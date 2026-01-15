"""Graph execution engine inspired by LangGraph.

Provides a declarative way to define agent workflows with:
- Nodes: Functions that process state
- Edges: Connections between nodes (sequential, conditional, parallel)
- State: TypedDict with optional reducers for parallel execution

Example:
    from omni_agent.core.graph import StateGraph, START, END
    from typing import TypedDict, Annotated
    import operator

    class MyState(TypedDict):
        messages: Annotated[list[str], operator.add]
        result: str

    def node_a(state: MyState) -> dict:
        return {"messages": ["A executed"]}

    def node_b(state: MyState) -> dict:
        return {"messages": ["B executed"], "result": "done"}

    graph = StateGraph(MyState)
    graph.add_node("a", node_a)
    graph.add_node("b", node_b)
    graph.add_edge(START, "a")
    graph.add_edge("a", "b")
    graph.add_edge("b", END)

    app = graph.compile()
    result = await app.invoke({"messages": [], "result": ""})
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    Generic,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
    get_type_hints,
    get_origin,
)

logger = logging.getLogger(__name__)

START = "__start__"
END = "__end__"

StateType = TypeVar("StateType", bound=Dict[str, Any])

NodeFunc = Callable[[Any], Union[Dict[str, Any], Coroutine[Any, Any, Dict[str, Any]]]]
ConditionFunc = Callable[[Any], str]


class EdgeType(Enum):
    NORMAL = "normal"
    CONDITIONAL = "conditional"


@dataclass
class Edge:
    source: str
    target: str
    edge_type: EdgeType = EdgeType.NORMAL
    condition: Optional[ConditionFunc] = None
    condition_map: Optional[Dict[str, str]] = None


@dataclass
class Node:
    name: str
    func: NodeFunc
    metadata: Dict[str, Any] = field(default_factory=dict)


def get_reducer(state_type: type, key: str) -> Optional[Callable[[Any, Any], Any]]:
    """Extract reducer function from Annotated type hints."""
    try:
        hints = get_type_hints(state_type, include_extras=True)
        hint = hints.get(key)
        if hint is None:
            return None

        origin = get_origin(hint)
        if origin is not None:
            from typing import Annotated
            if hasattr(hint, "__metadata__"):
                for meta in hint.__metadata__:
                    if callable(meta):
                        return meta
        return None
    except Exception:
        return None


def merge_state(
    current: Dict[str, Any],
    update: Dict[str, Any],
    state_type: type,
) -> Dict[str, Any]:
    """Merge state update into current state, applying reducers where defined."""
    result = current.copy()
    for key, value in update.items():
        reducer = get_reducer(state_type, key)
        if reducer is not None and key in result:
            result[key] = reducer(result[key], value)
        else:
            result[key] = value
    return result


class CompiledGraph(Generic[StateType]):
    """Compiled graph ready for execution."""

    def __init__(
        self,
        nodes: Dict[str, Node],
        edges: List[Edge],
        state_type: type,
        entry_point: str,
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._state_type = state_type
        self._entry_point = entry_point
        self._adjacency: Dict[str, List[Edge]] = {}
        self._build_adjacency()

    def _build_adjacency(self) -> None:
        """Build adjacency list from edges."""
        for edge in self._edges:
            if edge.source not in self._adjacency:
                self._adjacency[edge.source] = []
            self._adjacency[edge.source].append(edge)

    def _get_next_nodes(self, current: str, state: Dict[str, Any]) -> List[str]:
        """Determine next nodes based on edges and conditions."""
        edges = self._adjacency.get(current, [])
        next_nodes = []

        for edge in edges:
            if edge.edge_type == EdgeType.NORMAL:
                next_nodes.append(edge.target)
            elif edge.edge_type == EdgeType.CONDITIONAL:
                if edge.condition:
                    result = edge.condition(state)
                    if edge.condition_map:
                        target = edge.condition_map.get(result, result)
                    else:
                        target = result
                    if target != END:
                        next_nodes.append(target)
                    elif target == END:
                        next_nodes.append(END)

        return next_nodes

    async def _execute_node(self, node_name: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single node and return state update."""
        if node_name == END:
            return {}

        node = self._nodes.get(node_name)
        if node is None:
            raise ValueError(f"Node '{node_name}' not found")

        logger.debug("Executing node: %s", node_name)

        result = node.func(state)
        if asyncio.iscoroutine(result):
            result = await result

        return result if result else {}

    def _get_start_nodes(self) -> List[str]:
        """Get all nodes connected from START."""
        start_edges = self._adjacency.get(START, [])
        return [e.target for e in start_edges if e.edge_type == EdgeType.NORMAL]

    async def invoke(
        self,
        initial_state: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute the graph with initial state.

        Args:
            initial_state: Initial state dictionary
            config: Optional configuration

        Returns:
            Final state after graph execution
        """
        state = dict(initial_state)
        start_nodes = self._get_start_nodes()
        current_nodes = start_nodes if start_nodes else [self._entry_point]
        visited: Set[str] = set()
        max_iterations = config.get("max_iterations", 100) if config else 100
        iteration = 0

        while current_nodes and iteration < max_iterations:
            iteration += 1

            executable = [n for n in current_nodes if n != END and n not in visited]

            if not executable:
                if END in current_nodes:
                    break
                break

            if len(executable) == 1:
                node_name = executable[0]
                update = await self._execute_node(node_name, state)
                state = merge_state(state, update, self._state_type)
                visited.add(node_name)
                current_nodes = self._get_next_nodes(node_name, state)
            else:
                tasks = [self._execute_node(n, state) for n in executable]
                updates = await asyncio.gather(*tasks)

                for update in updates:
                    state = merge_state(state, update, self._state_type)

                visited.update(executable)

                next_set: Set[str] = set()
                for node_name in executable:
                    next_set.update(self._get_next_nodes(node_name, state))
                current_nodes = list(next_set)

        if iteration >= max_iterations:
            logger.warning("Graph execution reached max iterations: %d", max_iterations)

        return state

    async def stream(
        self,
        initial_state: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ):
        """Stream graph execution events.

        Yields:
            Dict with node execution results
        """
        state = dict(initial_state)
        start_nodes = self._get_start_nodes()
        current_nodes = start_nodes if start_nodes else [self._entry_point]
        visited: Set[str] = set()
        max_iterations = config.get("max_iterations", 100) if config else 100
        iteration = 0

        while current_nodes and iteration < max_iterations:
            iteration += 1

            executable = [n for n in current_nodes if n != END and n not in visited]

            if not executable:
                break

            for node_name in executable:
                yield {"type": "node_start", "node": node_name, "state": dict(state)}

                update = await self._execute_node(node_name, state)
                state = merge_state(state, update, self._state_type)
                visited.add(node_name)

                yield {
                    "type": "node_end",
                    "node": node_name,
                    "update": update,
                    "state": dict(state),
                }

            next_set: Set[str] = set()
            for node_name in executable:
                next_set.update(self._get_next_nodes(node_name, state))
            current_nodes = list(next_set)

        yield {"type": "done", "state": dict(state)}

    def get_graph_structure(self) -> Dict[str, Any]:
        """Return graph structure for visualization."""
        return {
            "nodes": list(self._nodes.keys()),
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "type": e.edge_type.value,
                }
                for e in self._edges
            ],
            "entry_point": self._entry_point,
        }


class StateGraph(Generic[StateType]):
    """Graph builder for defining agent workflows.

    Example:
        graph = StateGraph(MyState)
        graph.add_node("process", process_func)
        graph.add_edge(START, "process")
        graph.add_edge("process", END)
        app = graph.compile()
    """

    def __init__(self, state_type: type) -> None:
        """Initialize StateGraph.

        Args:
            state_type: TypedDict class defining the state schema
        """
        self._state_type = state_type
        self._nodes: Dict[str, Node] = {}
        self._edges: List[Edge] = []
        self._entry_point: Optional[str] = None

    def add_node(
        self,
        name: Union[str, NodeFunc],
        func: Optional[NodeFunc] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "StateGraph[StateType]":
        """Add a node to the graph.

        Args:
            name: Node name or function (if function, name is inferred)
            func: Node function (optional if name is a function)
            metadata: Optional metadata for the node

        Returns:
            Self for chaining
        """
        node_name: str
        node_func: NodeFunc

        if callable(name) and func is None:
            node_func = name
            node_name = name.__name__
        elif isinstance(name, str) and func is not None:
            node_name = name
            node_func = func
        else:
            raise ValueError("Node function is required")

        if node_name in self._nodes:
            raise ValueError(f"Node '{node_name}' already exists")

        self._nodes[node_name] = Node(
            name=node_name,
            func=node_func,
            metadata=metadata or {},
        )

        return self

    def add_edge(
        self,
        source: str,
        target: str,
    ) -> "StateGraph[StateType]":
        """Add a direct edge between nodes.

        Args:
            source: Source node name (or START)
            target: Target node name (or END)

        Returns:
            Self for chaining
        """
        if source == START:
            self._entry_point = target

        self._edges.append(Edge(
            source=source,
            target=target,
            edge_type=EdgeType.NORMAL,
        ))

        return self

    def add_conditional_edges(
        self,
        source: str,
        condition: ConditionFunc,
        path_map: Optional[Union[Dict[str, str], List[str]]] = None,
    ) -> "StateGraph[StateType]":
        """Add conditional edges from a node.

        Args:
            source: Source node name
            condition: Function that takes state and returns next node name
            path_map: Optional mapping from condition results to node names,
                     or list of possible target nodes

        Returns:
            Self for chaining

        Example:
            def route(state):
                return "yes" if state["should_continue"] else "no"

            graph.add_conditional_edges(
                "decide",
                route,
                {"yes": "continue_node", "no": END}
            )
        """
        condition_map = None
        if isinstance(path_map, list):
            condition_map = {name: name for name in path_map}
        elif isinstance(path_map, dict):
            condition_map = path_map

        self._edges.append(Edge(
            source=source,
            target="",
            edge_type=EdgeType.CONDITIONAL,
            condition=condition,
            condition_map=condition_map,
        ))

        return self

    def set_entry_point(self, node_name: str) -> "StateGraph[StateType]":
        """Set the entry point of the graph.

        Args:
            node_name: Name of the entry node

        Returns:
            Self for chaining
        """
        self._entry_point = node_name
        return self

    def compile(self) -> CompiledGraph[StateType]:
        """Compile the graph into an executable form.

        Returns:
            CompiledGraph ready for execution

        Raises:
            ValueError: If graph is invalid (no entry point, missing nodes)
        """
        if self._entry_point is None:
            for edge in self._edges:
                if edge.source == START:
                    self._entry_point = edge.target
                    break

        if self._entry_point is None:
            raise ValueError("No entry point defined. Use add_edge(START, 'node') or set_entry_point()")

        if self._entry_point not in self._nodes and self._entry_point != END:
            raise ValueError(f"Entry point '{self._entry_point}' is not a valid node")

        for edge in self._edges:
            if edge.edge_type == EdgeType.NORMAL:
                if edge.source != START and edge.source not in self._nodes:
                    raise ValueError(f"Edge source '{edge.source}' is not a valid node")
                if edge.target != END and edge.target not in self._nodes:
                    raise ValueError(f"Edge target '{edge.target}' is not a valid node")

        return CompiledGraph(
            nodes=self._nodes,
            edges=self._edges,
            state_type=self._state_type,
            entry_point=self._entry_point,
        )

    def get_nodes(self) -> List[str]:
        """Get list of node names."""
        return list(self._nodes.keys())

    def get_edges(self) -> List[Tuple[str, str]]:
        """Get list of edges as (source, target) tuples."""
        return [(e.source, e.target) for e in self._edges if e.edge_type == EdgeType.NORMAL]


class GraphBuilder(StateGraph[StateType]):
    """Alias for StateGraph for compatibility."""
    pass
