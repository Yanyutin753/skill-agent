import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Chat from './pages/Chat';
import Knowledge from './pages/Knowledge';
import { ErrorBoundary } from './components/ErrorBoundary';

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Chat />} />
          <Route path="/knowledge" element={<Knowledge />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;
