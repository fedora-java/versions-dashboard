package main

import (
	"html/template"
)

var Template = template.Must(template.ParseGlob("*.html"))
