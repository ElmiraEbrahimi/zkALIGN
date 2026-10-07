// zkalign-eval executes exactly one measured stage per operating-system process.
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"time"

	"github.com/ElmiraEbrahimi/zkALIGN/circuit"
	"github.com/ElmiraEbrahimi/zkALIGN/hashing"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/logger"
)

type measurement struct {
	Stage       string           `json:"stage"`
	StartNS     int64            `json:"start_ns"`
	EndNS       int64            `json:"end_ns"`
	Seconds     float64          `json:"operation_seconds"`
	Status      string           `json:"status"`
	Error       string           `json:"error,omitempty"`
	Constraints int              `json:"constraints,omitempty"`
	Bytes       map[string]int64 `json:"bytes,omitempty"`
	GOMAXPROCS  int              `json:"gomaxprocs"`
	Details     any              `json:"details,omitempty"`
}

func readJSON(p string, v any) error {
	b, e := os.ReadFile(p)
	if e != nil {
		return e
	}
	return json.Unmarshal(b, v)
}
func writeJSON(p string, v any) error {
	b, e := json.MarshalIndent(v, "", "  ")
	if e != nil {
		return e
	}
	return os.WriteFile(p, b, 0600)
}
func readObject(p string, v io.ReaderFrom) error {
	f, e := os.Open(p)
	if e != nil {
		return e
	}
	defer f.Close()
	_, e = v.ReadFrom(f)
	return e
}
func writeObject(p string, v io.WriterTo) (int64, error) {
	f, e := os.OpenFile(p, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600)
	if e != nil {
		return 0, e
	}
	defer f.Close()
	return v.WriteTo(f)
}
func measure(m *measurement, fn func() error) error {
	start := time.Now()
	m.StartNS = start.UnixNano()
	err := fn()
	m.EndNS = time.Now().UnixNano()
	m.Seconds = time.Since(start).Seconds()
	return err
}
func main() {
	stage := flag.String("stage", "", "compile/setup/prepare/context/witness/prove/verify/audit/solve/hash")
	dir := flag.String("dir", "", "configuration work directory")
	casePath := flag.String("case", "", "prepared private case JSON")
	k := flag.Int("threshold", 1, "public threshold")
	result := flag.String("result", "", "measurement JSON")
	prefix := flag.String("prefix", "case", "artifact prefix")
	input := flag.String("input", "", "input file (hash)")
	population := flag.Int("population", 100, "synthetic roster size for root-only benchmark")
	flag.Parse()
	logger.Disable()
	m := measurement{Stage: *stage, Status: "ok", Bytes: map[string]int64{}, GOMAXPROCS: runtime.GOMAXPROCS(0)}
	var e error
	if *stage == "population-root" {
		e = populationRoot(*population, &m)
	} else {
		e = run(*stage, *dir, *casePath, *prefix, *input, *k, &m)
	}
	if e != nil {
		m.Status = "error"
		m.Error = e.Error()
	}
	if *result != "" {
		if err := writeJSON(*result, m); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
	}
	b, _ := json.Marshal(m)
	fmt.Println(string(b))
	if e != nil {
		os.Exit(1)
	}
}
func run(stage, dir, casePath, prefix, input string, k int, m *measurement) error {
	if stage == "hash" {
		data, e := os.ReadFile(input)
		if e != nil {
			return e
		}
		return measure(m, func() error { m.Details = hashing.File(data); return nil })
	}
	if e := os.MkdirAll(dir, 0700); e != nil {
		return e
	}
	path := func(s string) string { return filepath.Join(dir, s) }
	cfg, e := circuit.LoadModelConfig(path("config.json"))
	if e != nil {
		return e
	}
	cs := groth16.NewCS(ecc.BN254)
	switch stage {
	case "integrity":
		rows, err := integrity(dir, cfg)
		m.Details = rows
		if err != nil {
			return err
		}
		for _, r := range rows {
			if r.Unexpected != 0 {
				return fmt.Errorf("unexpected integrity outcome: %s", r.Operator)
			}
		}
		return nil
	case "compile":
		e = measure(m, func() error {
			var err error
			cs, err = frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, circuit.NewConfiguredCircuit(cfg))
			return err
		})
		if e != nil {
			return e
		}
		m.Constraints = cs.GetNbConstraints()
		m.Bytes["r1cs"], e = writeObject(path("circuit.r1cs"), cs)
		return e
	case "setup":
		if e = readObject(path("circuit.r1cs"), cs); e != nil {
			return e
		}
		var pk groth16.ProvingKey
		var vk groth16.VerifyingKey
		e = measure(m, func() error { var err error; pk, vk, err = groth16.Setup(cs); return err })
		if e != nil {
			return e
		}
		m.Bytes["pk"], e = writeObject(path("proving.key"), pk)
		if e != nil {
			return e
		}
		m.Bytes["vk"], e = writeObject(path("verification.key"), vk)
		if e != nil {
			return e
		}
		b, e := os.ReadFile(path("verification.key"))
		if e != nil {
			return e
		}
		m.Details = hashing.VerificationKey(b)
		return nil
	case "prepare":
		var cases []circuit.EvaluationCase
		if e = readJSON(path("cases.json"), &cases); e != nil {
			return e
		}
		var roster []circuit.AuditCase
		var root string
		e = measure(m, func() error {
			var err error
			cases, roster, root, err = circuit.PrepareConfiguredPopulation(cfg, cases)
			return err
		})
		if e != nil {
			return e
		}
		for _, c := range cases {
			if e = writeJSON(path(fmt.Sprintf("private-%d.json", c.Index)), c); e != nil {
				return e
			}
		}
		return writeJSON(path("population.json"), circuit.AuditManifest{Version: circuit.AuditVersion, Root: root, Cases: roster})
	case "context":
		var manifest circuit.AuditManifest
		if e = readJSON(path("population.json"), &manifest); e != nil {
			return e
		}
		vk, e := os.ReadFile(path("verification.key"))
		if e != nil {
			return e
		}
		manifest.Threshold = k
		manifest.TargetPercent = 95
		manifest.VerificationKeyMiMC = hashing.VerificationKey(vk)
		if e = measure(m, manifest.Validate); e != nil {
			return e
		}
		if e = writeJSON(path(fmt.Sprintf("manifest-%d.json", k)), manifest); e != nil {
			return e
		}
		data, e := os.ReadFile(path(fmt.Sprintf("manifest-%d.json", k)))
		if e != nil {
			return e
		}
		return os.WriteFile(path(fmt.Sprintf("manifest-%d.mimc", k)), []byte(hashing.Manifest(data)), 0600)
	case "witness", "solve":
		var c circuit.EvaluationCase
		if e = readJSON(casePath, &c); e != nil {
			return e
		}
		if stage == "solve" {
			if e = readObject(path("circuit.r1cs"), cs); e != nil {
				return e
			}
		}
		var w witness.Witness
		e = measure(m, func() error {
			a, err := c.Assignment(cfg, k)
			if err != nil {
				return err
			}
			w, err = frontend.NewWitness(a, ecc.BN254.ScalarField())
			if err != nil {
				return err
			}
			if stage == "solve" {
				return cs.IsSolved(w)
			}
			return nil
		})
		if e != nil {
			return e
		}
		if stage == "witness" {
			m.Bytes["witness"], e = writeObject(path(prefix+".wtns"), w)
		}
		return e
	case "prove":
		if e = readObject(path("circuit.r1cs"), cs); e != nil {
			return e
		}
		pk := groth16.NewProvingKey(ecc.BN254)
		if e = readObject(path("proving.key"), pk); e != nil {
			return e
		}
		w, err := witness.New(ecc.BN254.ScalarField())
		if err != nil {
			return err
		}
		if e = readObject(path(prefix+".wtns"), w); e != nil {
			return e
		}
		var proof groth16.Proof
		e = measure(m, func() error { var err error; proof, err = groth16.Prove(cs, pk, w); return err })
		if e != nil {
			return e
		}
		var buf bytes.Buffer
		m.Bytes["proof"], e = proof.WriteTo(&buf)
		if e != nil {
			return e
		}
		var c circuit.EvaluationCase
		if e = readJSON(casePath, &c); e != nil {
			return e
		}
		digest, e := os.ReadFile(path(fmt.Sprintf("manifest-%d.mimc", k)))
		if e != nil {
			return e
		}
		bundle := circuit.AuditProofBundle{ManifestMiMC: string(digest), Commitment: c.Commitment, Proof: buf.Bytes()}
		if e = writeJSON(path(prefix+".proof.json"), bundle); e != nil {
			return e
		}
		info, e := os.Stat(path(prefix + ".proof.json"))
		if e != nil {
			return e
		}
		m.Bytes["bundle"] = info.Size()
		return nil
	case "verify", "audit":
		manifest, e := os.ReadFile(path(fmt.Sprintf("manifest-%d.json", k)))
		if e != nil {
			return e
		}
		digest, e := os.ReadFile(path(fmt.Sprintf("manifest-%d.mimc", k)))
		if e != nil {
			return e
		}
		vk, e := os.ReadFile(path("verification.key"))
		if e != nil {
			return e
		}
		verifier, e := circuit.NewAuditVerifier(manifest, string(digest), vk)
		if e != nil {
			return e
		}
		files := []string{path(prefix + ".proof.json")}
		if stage == "audit" {
			files, e = filepath.Glob(path(fmt.Sprintf("k%d-*.proof.json", k)))
			if e != nil {
				return e
			}
		}
		blobs := make([][]byte, len(files))
		for j, f := range files {
			blobs[j], e = os.ReadFile(f)
			if e != nil {
				return e
			}
		}
		e = measure(m, func() error {
			for j, f := range files {
				verifier.Check(filepath.Base(f), blobs[j])
			}
			return nil
		})
		report := verifier.Report()
		m.Details = report
		for _, r := range report.Receipts {
			if r.Status == "invalid" {
				return fmt.Errorf("invalid proof: %s", r.Reason)
			}
		}
		return e
	default:
		return fmt.Errorf("unknown stage %q", stage)
	}
}
