// Reference hash utility used for cross-language compatibility checks.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/ElmiraEbrahimi/zkALIGN/circuit"
	"github.com/ElmiraEbrahimi/zkALIGN/hashing"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
)

func main() {
	constants := flag.Bool("constants", false, "print gnark BN254 MiMC round constants")
	file := flag.String("file", "", "print MiMC file fingerprint")
	records := flag.String("records", "", "print circuit-compatible root and commitments")
	flag.Parse()
	if *constants {
		if err := json.NewEncoder(os.Stdout).Encode(mimc.GetConstants()); err != nil {
			log.Fatal(err)
		}
		return
	}
	if *file != "" {
		data, err := os.ReadFile(*file)
		if err != nil {
			log.Fatal(err)
		}
		fmt.Println(hashing.File(data))
		return
	}
	if *records != "" {
		root, entries, _, err := circuit.PrepareAuditPopulation(*records)
		if err != nil {
			log.Fatal(err)
		}
		if err := json.NewEncoder(os.Stdout).Encode(map[string]any{"root": root, "cases": entries}); err != nil {
			log.Fatal(err)
		}
		return
	}
	log.Fatal("specify -constants, -file or -records")
}
