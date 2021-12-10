package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
)

type VersionCell struct {
	Repeat  int
	Version Version
	Base    Version
}

type Versions struct {
	Versions map[string]struct {
		Upstream struct {
			Latest Version
			Stable Version `json:"latest-stable"`
		}
		JPB        Version `json:"jp-bootstrap"`
		JpbNorm    VersionCell
		Fedora     map[string]Version
		Normalized []VersionCell
	}
	Columns struct {
		Fedora []string
	} `json:"version-columns"`
	Hostname string
	Time     string `json:"time-generated"`
}

func (cell VersionCell) Class() string {
	cmp := cell.Version.RpmVerCmp(cell.Base)
	if cmp < 0 {
		return "downgrade"
	}
	if cmp > 0 {
		return "upgrade"
	}
	return ""
}

func handler(w http.ResponseWriter, r *http.Request) {
	url := os.Getenv("VERSIONS_JSON_URL")
	if url == "" {
		url = "https://versions.kjnet.xyz/versions.json"
	}
	resp, err := http.Get(url)
	if err != nil {
		log.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		resp.Body.Close()
		log.Fatal(fmt.Errorf("HTTP GET failed: %s", resp.Status))
	}
	var result Versions
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		resp.Body.Close()
		log.Fatal(err)
	}
	for key, val := range result.Versions {
		cur := VersionCell{}
		x := []VersionCell{}
		for _, fv := range result.Columns.Fedora {
			v := val.Fedora[fv]
			if cur.Repeat != 0 && v != cur.Version {
				//cur.Base = v
				cur.Base = cur.Version
				x = append(x, cur)
				cur.Repeat = 0
			}
			cur.Version = v
			cur.Repeat++
		}
		cur.Base = val.Upstream.Stable
		val.JpbNorm = VersionCell{1, val.JPB, cur.Version}
		val.Normalized = append(x, cur)
		result.Versions[key] = val
	}
	w.Header().Add("Content-Type", "text/html")
	err = Template.Execute(w, result)
	if err != nil {
		fmt.Println(err)
	}
}

func main() {
	http.HandleFunc("/", handler)
	http.ListenAndServe(":8080", nil)
}
