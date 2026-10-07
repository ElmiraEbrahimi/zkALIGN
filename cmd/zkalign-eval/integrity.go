package main

import (
	"encoding/json"
	"fmt"
	"math/rand"
	"os"
	"path/filepath"
	"sort"

	"github.com/ElmiraEbrahimi/zkALIGN/circuit"
	"github.com/ElmiraEbrahimi/zkALIGN/hashing"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
)

type integrityResult struct {
	Operator   string `json:"operator"`
	Mode       string `json:"mode"`
	Attempts   int    `json:"attempts"`
	Expected   string `json:"expected"`
	Unexpected int    `json:"unexpected"`
	Skipped    int    `json:"skipped"`
}

func integrity(dir string, cfg *circuit.ModelConfig) ([]integrityResult, error) {
	cs := groth16.NewCS(ecc.BN254)
	if err := readObject(filepath.Join(dir, "circuit.r1cs"), cs); err != nil {
		return nil, err
	}
	files, err := filepath.Glob(filepath.Join(dir, "private-*.json"))
	if err != nil {
		return nil, err
	}
	sort.Strings(files)
	rand.New(rand.NewSource(42)).Shuffle(len(files), func(i, j int) { files[i], files[j] = files[j], files[i] })
	operators := []string{"valid_control", "trace_change", "trace_add", "trace_remove", "trace_swap", "path_change", "skip_consumed_event", "reorder_consuming_rows", "invalid_transition", "disabled_transition",
		"wrong_sync_label", "truncate", "wrong_cost", "understated_cost", "above_threshold", "bad_padding", "bad_length", "bad_move_type", "bad_index"}
	rows := make([]integrityResult, len(operators))
	for i, name := range operators {
		expect := "reject"
		if name == "valid_control" {
			expect = "accept"
		}
		rows[i] = integrityResult{Operator: name, Mode: "r1cs_solver", Expected: expect}
	}
	count := 0
	for _, file := range files {
		var c circuit.EvaluationCase
		if err := readJSON(file, &c); err != nil {
			return nil, err
		}
		if c.Cost == nil || len(c.Moves) > cfg.AlignmentCapacity {
			continue
		}
		count++
		if count > 50 {
			break
		}
		for n, name := range operators {
			a, err := c.Assignment(cfg, *c.Cost)
			if err != nil {
				return nil, err
			}
			applicable := true
			switch name {
			case "trace_change":
				if len(c.Events) == 0 || cfg.ActivityCount < 2 {
					applicable = false
				} else {
					a.TraceEvents[0] = c.Events[0]%cfg.ActivityCount + 1
				}
			case "trace_add":
				if len(c.Events) >= cfg.TraceCapacity {
					applicable = false
				} else {
					a.TraceEvents[len(c.Events)] = 1
					a.TraceLength = len(c.Events) + 1
				}
			case "trace_remove":
				if len(c.Events) == 0 {
					applicable = false
				} else {
					a.TraceLength = len(c.Events) - 1
					a.TraceEvents[len(c.Events)-1] = 0
				}
			case "path_change":
				a.MerklePath[0] = "1"
			case "trace_swap":
				j := -1
				for n := 1; n < len(c.Events); n++ {
					if c.Events[n] != c.Events[0] {
						j = n
						break
					}
				}
				if j < 0 {
					applicable = false
				} else {
					a.TraceEvents[0], a.TraceEvents[j] = a.TraceEvents[j], a.TraceEvents[0]
				}
			case "reorder_consuming_rows":
				first, second := -1, -1
				for n, row := range c.Moves {
					if row.Type != 1 && row.Type != 2 {
						continue
					}
					if first < 0 {
						first = n
					} else if row.Activity != c.Moves[first].Activity {
						second = n
						break
					}
				}
				if second < 0 {
					applicable = false
				} else {
					a.AlignmentMoveTypes[first], a.AlignmentMoveTypes[second] = a.AlignmentMoveTypes[second], a.AlignmentMoveTypes[first]
					a.AlignmentActivities[first], a.AlignmentActivities[second] = a.AlignmentActivities[second], a.AlignmentActivities[first]
					a.ModelTransitionIDs[first], a.ModelTransitionIDs[second] = a.ModelTransitionIDs[second], a.ModelTransitionIDs[first]
				}
			case "disabled_transition":
				j := -1
				for n, r := range c.Moves {
					if r.Type == 1 || r.Type == 3 {
						j = n
						break
					}
				}
				disabled := -1
				for p, list := range cfg.Inputs {
					if cfg.Initial[p] == 0 && len(list) > 0 {
						disabled = list[0] + 1
						break
					}
				}
				if j < 0 || disabled < 0 {
					applicable = false
				} else {
					a.ModelTransitionIDs[j] = disabled
				}
			case "skip_consumed_event":
				j := -1
				for n, m := range c.Moves {
					if m.Type == 1 || m.Type == 2 {
						j = n
						break
					}
				}
				if j < 0 {
					applicable = false
				} else {
					copy(a.AlignmentMoveTypes[j:], a.AlignmentMoveTypes[j+1:])
					copy(a.AlignmentActivities[j:], a.AlignmentActivities[j+1:])
					copy(a.ModelTransitionIDs[j:], a.ModelTransitionIDs[j+1:])
					last := cfg.AlignmentCapacity - 1
					a.AlignmentMoveTypes[last] = 0
					a.AlignmentActivities[last] = 0
					a.ModelTransitionIDs[last] = 0
					a.AlignmentLength = len(c.Moves) - 1
				}
			case "invalid_transition":
				if len(c.Moves) == 0 {
					applicable = false
				} else {
					a.ModelTransitionIDs[0] = len(cfg.Labels) + 1
				}
			case "wrong_sync_label":
				j := -1
				for n, m := range c.Moves {
					if m.Type == 1 {
						j = n
						break
					}
				}
				if j < 0 || cfg.ActivityCount < 2 {
					applicable = false
				} else {
					a.AlignmentActivities[j] = c.Moves[j].Activity%cfg.ActivityCount + 1
				}
			case "truncate":
				if len(c.Moves) == 0 {
					applicable = false
				} else {
					// Remove the entire model execution, not merely a dispensable last loop.
					for j := range a.AlignmentMoveTypes {
						a.AlignmentMoveTypes[j] = 0
						a.AlignmentActivities[j] = 0
						a.ModelTransitionIDs[j] = 0
					}
					a.AlignmentLength = 0
					if len(c.Events) == 0 {
						applicable = false
					}
				}
			case "wrong_cost":
				a.AlignmentCost = *c.Cost + 1
			case "understated_cost":
				if *c.Cost == 0 {
					applicable = false
				} else {
					a.AlignmentCost = *c.Cost - 1
					a.CostThreshold = *c.Cost - 1
				}
			case "above_threshold":
				if *c.Cost == 0 {
					applicable = false
				} else {
					a.CostThreshold = *c.Cost - 1
				}
			case "bad_padding":
				if len(c.Moves) >= cfg.AlignmentCapacity {
					applicable = false
				} else {
					a.AlignmentActivities[len(c.Moves)] = 1
				}
			case "bad_length":
				a.AlignmentLength = len(c.Moves) + 1
			case "bad_move_type":
				a.AlignmentMoveTypes[0] = 4
			case "bad_index":
				a.TraceIndex = "4294967296"
			}
			if !applicable {
				rows[n].Skipped++
				continue
			}
			rows[n].Attempts++
			w, err := frontend.NewWitness(a, ecc.BN254.ScalarField())
			if err != nil {
				return nil, err
			}
			solved := cs.IsSolved(w) == nil
			if solved != (name == "valid_control") {
				rows[n].Unexpected++
			}
		}
	}
	// Use an actual accepted proof, not a synthetic "accepted" counter.
	proofs, err := filepath.Glob(filepath.Join(dir, "k1-*.proof.json"))
	if err != nil {
		return nil, err
	}
	if len(proofs) == 0 {
		return rows, fmt.Errorf("audit integrity needs at least one real proof")
	}
	data, err := os.ReadFile(filepath.Join(dir, "manifest-1.json"))
	if err != nil {
		return nil, err
	}
	vk, err := os.ReadFile(filepath.Join(dir, "verification.key"))
	if err != nil {
		return nil, err
	}
	proof, err := os.ReadFile(proofs[0])
	if err != nil {
		return nil, err
	}
	var bundle circuit.AuditProofBundle
	if err = json.Unmarshal(proof, &bundle); err != nil {
		return nil, err
	}
	record := func(name, mode, expect string, good bool) {
		r := integrityResult{Operator: name, Mode: mode, Attempts: 1, Expected: expect}
		if !good {
			r.Unexpected = 1
		}
		rows = append(rows, r)
	}
	verifier, err := circuit.NewAuditVerifier(data, hashing.Manifest(data), vk)
	if err != nil {
		return nil, err
	}
	verifier.Check("first", proof)
	before := verifier.Report().Certified
	verifier.Check("duplicate", proof)
	record("duplicate", "groth16_auditor", "count_unchanged", before == 1 && verifier.Report().Certified == 1)
	bad := bundle
	bad.ManifestMiMC = "wrong"
	badBytes, _ := json.Marshal(bad)
	v, err := circuit.NewAuditVerifier(data, hashing.Manifest(data), vk)
	if err != nil {
		return nil, err
	}
	v.Check("invalid", badBytes)
	record("wrong_context", "groth16_auditor", "reject", v.Report().Certified == 0)
	v.Check("valid_retry", proof)
	record("valid_after_invalid", "groth16_auditor", "accept", v.Report().Certified == 1)
	bad = bundle
	bad.Commitment = "0"
	badBytes, _ = json.Marshal(bad)
	v, _ = circuit.NewAuditVerifier(data, hashing.Manifest(data), vk)
	v.Check("unlisted", badBytes)
	record("unlisted_commitment", "groth16_auditor", "reject", v.Report().Certified == 0)
	for _, name := range []string{"removed_case", "extra_case", "gap", "swapped_commitments", "changed_root", "changed_threshold", "changed_key"} {
		var manifest circuit.AuditManifest
		json.Unmarshal(data, &manifest)
		switch name {
		case "removed_case":
			manifest.Cases = manifest.Cases[:len(manifest.Cases)-1]
		case "extra_case":
			manifest.Cases = append(manifest.Cases, circuit.AuditCase{Index: uint32(len(manifest.Cases)), Commitment: "42"})
		case "gap":
			manifest.Cases[0].Index = uint32(len(manifest.Cases) + 1)
		case "swapped_commitments":
			if len(manifest.Cases) < 2 {
				continue
			}
			manifest.Cases[0].Commitment, manifest.Cases[1].Commitment = manifest.Cases[1].Commitment, manifest.Cases[0].Commitment
		case "changed_root":
			manifest.Root = "1"
		case "changed_threshold":
			manifest.Threshold++
		case "changed_key":
			manifest.VerificationKeyMiMC = hashing.VerificationKey([]byte("wrong"))
		}
		altered, _ := json.Marshal(manifest)
		_, err := circuit.NewAuditVerifier(altered, hashing.Manifest(data), vk)
		good := err != nil
		if name != "changed_threshold" && name != "changed_key" {
			good = good && manifest.Validate() != nil
		}
		record(name, "auditor_context", "reject", good)
	}
	return rows, nil
}
