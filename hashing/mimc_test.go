package hashing

import (
	"testing"
)

func TestByteFraming(t *testing.T) {
	seen := map[string]bool{}
	for _, parts := range [][][]byte{nil, {{}}, {{0}}, {{0, 0}}, {{1}}, {{0, 1}}, {{1, 0}}, {{1}, {2}}, {{1, 2}}} {
		digest := Hex(parts...)
		if seen[digest] {
			t.Fatal("distinct byte framings collide")
		}
		seen[digest] = true
	}
	if Manifest([]byte("x")) == VerificationKey([]byte("x")) || Manifest([]byte("x")) == File([]byte("x")) {
		t.Fatal("hash domains not separated")
	}
}
