# Bubble Sort Implementation in Cy
# Demonstrates: while loops, indexed assignment, break, compound assignments

# Get the array to sort from input
arr = input.array

# Validate input
if (len(arr) == 0) {
    return {"error": "Array is empty", "sorted": []}
}

n = len(arr)

# Bubble sort with early exit optimization
i = 0
while (i < n - 1) {
    swapped = False

    # Compare adjacent elements
    j = 0
    while (j < n - i - 1) {
        if (arr[j] > arr[j + 1]) {
            # Swap using indexed assignment
            tmp = arr[j]
            arr[j] = arr[j + 1]
            arr[j + 1] = tmp
            swapped = True
        }
        j += 1
    }

    # If no swaps occurred, array is already sorted
    if (not swapped) {
        break
    }
    i += 1
}

# Return the sorted array with metadata
return {
    "original": input.array,
    "sorted": arr,
    "length": n,
    "algorithm": "bubble_sort"
}
