package main

import "fmt"

// ComputeOrderTotal sums line totals (Go grammar must load from the wheel).
func ComputeOrderTotal(items []int) int {
	t := 0
	for _, v := range items {
		t += v
	}
	return t
}

func main() {
	fmt.Println(ComputeOrderTotal([]int{1, 2, 3}))
}
