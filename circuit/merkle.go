package circuit

import (
	"bufio"
	"encoding/json"
	"fmt"
	"math/big"
	"os"

	"github.com/ElmiraEbrahimi/zkALIGN/hashing"
)

type privateTraceRecord struct {
	HashScheme  string `json:"hash_scheme"`
	Index       uint32 `json:"index"`
	CaseID      string `json:"case_id"`
	ActivityIDs []int  `json:"activity_ids"`
	Salt        string `json:"salt"`
}

type circuitMerkleProof struct {
	Root     *big.Int
	Siblings [MerkleTreeDepth]*big.Int
}

// RootForAuditCases shares the exact witness tree construction. Callers still
// use AuditManifest.Validate to enforce contiguous indices and uniqueness.
func RootForAuditCases(cases []AuditCase) (string, error) {
	leaves := make(map[uint32]*big.Int, len(cases))
	for _, c := range cases {
		value, err := canonicalField(c.Commitment)
		if err != nil {
			return "", err
		}
		if _, exists := leaves[c.Index]; exists {
			return "", fmt.Errorf("duplicate index")
		}
		leaves[c.Index] = circuitMerkleLeaf(c.Index, value)
	}
	return buildCircuitMerkleProof(leaves, 0).Root.String(), nil
}

func circuitMerkleLeaf(index uint32, commitment *big.Int) *big.Int {
	return hashFieldElements(big.NewInt(DomainMerkleLeaf), new(big.Int).SetUint64(uint64(index)), commitment)
}

func loadCircuitMerkleProof(recordsPath string, targetIndex uint32) (circuitMerkleProof, error) {
	file, err := os.Open(recordsPath)
	if err != nil {
		return circuitMerkleProof{}, fmt.Errorf("open private trace records: %w", err)
	}
	defer file.Close()

	leaves := make(map[uint32]*big.Int)
	scanner := bufio.NewScanner(file)
	lineNumber := 0
	foundTarget := false
	for scanner.Scan() {
		lineNumber++
		var record privateTraceRecord
		if err := json.Unmarshal(scanner.Bytes(), &record); err != nil {
			return circuitMerkleProof{}, fmt.Errorf("decode private trace record line %d: %w", lineNumber, err)
		}
		if record.HashScheme != hashing.Scheme {
			return circuitMerkleProof{}, fmt.Errorf("legacy records require explicit MiMC migration")
		}
		if len(record.ActivityIDs) > MaxTraceEvents {
			return circuitMerkleProof{}, fmt.Errorf("case %s has %d events; commitment maximum is %d", record.CaseID, len(record.ActivityIDs), MaxTraceEvents)
		}
		salt, ok := new(big.Int).SetString(record.Salt, 16)
		if !ok {
			return circuitMerkleProof{}, fmt.Errorf("case %s has invalid hexadecimal salt", record.CaseID)
		}
		var trace [MaxTraceEvents]int
		copy(trace[:], record.ActivityIDs)
		commitment := ComputeTraceCommitment(len(record.ActivityIDs), trace, salt)
		leaf := circuitMerkleLeaf(record.Index, commitment)
		if _, exists := leaves[record.Index]; exists {
			return circuitMerkleProof{}, fmt.Errorf("duplicate trace index %d", record.Index)
		}
		leaves[record.Index] = leaf
		foundTarget = foundTarget || record.Index == targetIndex
	}
	if err := scanner.Err(); err != nil {
		return circuitMerkleProof{}, fmt.Errorf("read private trace records: %w", err)
	}
	if !foundTarget {
		return circuitMerkleProof{}, fmt.Errorf("trace index %d is absent from commitment records", targetIndex)
	}
	return buildCircuitMerkleProof(leaves, targetIndex), nil
}

// Shared tree construction for private witness paths and public audit rosters.
// Leaves are already indexed hashes. Defaults and level domains must remain
// identical to the circuit and append-only trace store.
func buildCircuitMerkleProof(leaves map[uint32]*big.Int, targetIndex uint32) circuitMerkleProof {
	defaultHashes := make([]*big.Int, MerkleTreeDepth+1)
	defaultHashes[0] = hashFieldElements(big.NewInt(DomainMerkleLeaf), big.NewInt(0), big.NewInt(0))
	for level := 0; level < MerkleTreeDepth; level++ {
		defaultHashes[level+1] = hashFieldElements(big.NewInt(int64(DomainMerkleNode+level)), defaultHashes[level], defaultHashes[level])
	}

	proof := circuitMerkleProof{}
	currentLevel := leaves
	targetNode := targetIndex
	for level := 0; level < MerkleTreeDepth; level++ {
		sibling, exists := currentLevel[targetNode^1]
		if !exists {
			sibling = defaultHashes[level]
		}
		proof.Siblings[level] = sibling

		parents := make(map[uint32]*big.Int)
		seenParents := make(map[uint32]struct{})
		for nodeIndex := range currentLevel {
			parentIndex := nodeIndex >> 1
			if _, seen := seenParents[parentIndex]; seen {
				continue
			}
			seenParents[parentIndex] = struct{}{}
			left, leftExists := currentLevel[parentIndex<<1]
			if !leftExists {
				left = defaultHashes[level]
			}
			right, rightExists := currentLevel[(parentIndex<<1)|1]
			if !rightExists {
				right = defaultHashes[level]
			}
			parents[parentIndex] = hashFieldElements(big.NewInt(int64(DomainMerkleNode+level)), left, right)
		}
		currentLevel = parents
		targetNode >>= 1
	}
	root, exists := currentLevel[0]
	if !exists {
		root = defaultHashes[MerkleTreeDepth]
	}
	proof.Root = root
	return proof
}
