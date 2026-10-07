package main

import (
	"fmt"
	"github.com/ElmiraEbrahimi/zkALIGN/circuit"
	"strconv"
	"strings"
)

func populationRoot(n int, m *measurement) error {
	if n < 1 || n > 1000000 {
		return fmt.Errorf("population outside benchmark limit")
	}
	// Synthetic distinct field commitments, not certificates or real-log cases.
	// This benchmark measures only public roster validation/root reconstruction.
	cases := make([]circuit.AuditCase, n)
	for i := range cases {
		cases[i] = circuit.AuditCase{Index: uint32(i), Commitment: strconv.Itoa(i + 1)}
	}
	root, err := circuit.RootForAuditCases(cases)
	if err != nil {
		return err
	}
	manifest := circuit.AuditManifest{Version: circuit.AuditVersion, Root: root, Cases: cases,
		Threshold: 1, TargetPercent: 95, VerificationKeyMiMC: strings.Repeat("0", 63) + "1"}
	m.Details = map[string]any{"N": n, "mode": "synthetic_roster_only", "distinct_proofs_verified": 0}
	return measure(m, manifest.Validate)
}
