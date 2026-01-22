def quicksort(arr):
    """
    Quicksort is a divide-and-conquer algorithm. 
    It works by selecting a 'pivot' element from the array and partitioning 
    the other elements into two sub-arrays, according to whether they are 
    less than or greater than the pivot.
    """
    if len(arr) <= 1:
        return arr
    else:
        # Choose the middle element as the pivot
        pivot = arr[len(arr) // 2]
        
        # Elements smaller than the pivot
        left = [x for x in arr if x < pivot]
        
        # Elements equal to the pivot
        middle = [x for x in arr if x == pivot]
        
        # Elements greater than the pivot
        right = [x for x in arr if x > pivot]
        
        # Recursively sort the sub-arrays and combine them
        return quicksort(left) + middle + quicksort(right)

if __name__ == "__main__":
    # Example usage
    sample_list = [3, 6, 8, 10, 1, 2, 1]
    print(f"Original list: {sample_list}")
    
    sorted_list = quicksort(sample_list)
    print(f"Sorted list:   {sorted_list}")

    # Another example
    another_list = [5, 2, 9, 1, 5, 6]
    print(f"
Original list: {another_list}")
    print(f"Sorted list:   {quicksort(another_list)}")
