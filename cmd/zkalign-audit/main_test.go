package main

import (
	"strings"
	"testing"
)

func TestInitializeRejectsSubsetFlag(t *testing.T) {
	// Reject the obsolete option during flag parsing, before reading records
	// or creating keys. There is no CLI route to select an easier population.
	err := initialize([]string{"-cases", "A,AG"})
	if err == nil || !strings.Contains(err.Error(), "flag provided but not defined") {
		t.Fatalf("expected removed subset flag to be rejected, got %v", err)
	}
}
