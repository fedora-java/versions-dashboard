package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
)

type Versions struct {
	Versions map[string]struct {
		Upstream struct {
			Latest string
			Stable string `json:"latest-stable"`
		}
		JPB    string `json:"jp-bootstrap"`
		Fedora map[string]string
	}
	Columns struct {
		Fedora []string
	} `json:"version-columns"`
	Hostname string
	Time     string `json:"time-generated"`
}

func handler(w http.ResponseWriter, r *http.Request) {
	url := "http://versions-json/versions.json"
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
