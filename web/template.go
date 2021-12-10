package main

import (
	"html/template"
)

var Template = template.Must(template.New("tpl").Parse(`
<!doctype html>
<html lang="en">
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="description" content="">
    <meta name="author" content="">
    <meta name="generator" content="">
    <title>Versions</title>
    <link href="https://mbi-artifacts.s3.eu-central-1.amazonaws.com/static/fontawesome/css/all.min.css" type="text/css" rel="stylesheet" />
    <link href="https://mbi-artifacts.s3.eu-central-1.amazonaws.com/static/bootstrap/css/bootstrap.min.css" type="text/css" rel="stylesheet" />
    <link href="https://mbi-artifacts.s3.eu-central-1.amazonaws.com/static/custom.css" rel="stylesheet" />
  </head>
  <body>
    <nav class="navbar navbar-expand-md navbar-dark bg-primary fixed-top">
      <div class="container-fluid">
        <svg class='logo' style='font-size:65px' height='47' width='150'>
          <svg y='0' height='4' width='150' viewbox='0 0 150 4'><text x='-6' y='47'>MBI</text></svg>
          <svg y='6' height='4' width='150' viewbox='0 6 150 4'><text x='-6' y='47'>MBI</text></svg>
          <svg y='12' height='4' width='150' viewbox='0 12 150 4'><text x='-6' y='47'>MBI</text></svg>
          <svg y='18' height='4' width='150' viewbox='0 18 150 4'><text x='-6' y='47'>MBI</text></svg>
          <svg y='24' height='4' width='150' viewbox='0 24 150 4'><text x='-6' y='47'>MBI</text></svg>
          <svg y='30' height='4' width='150' viewbox='0 30 150 4'><text x='-6' y='47'>MBI</text></svg>
          <svg y='36' height='4' width='150' viewbox='0 36 150 4'><text x='-6' y='47'>MBI</text></svg>
          <svg y='42' height='4' width='150' viewbox='0 42 150 4'><text x='-6' y='47'>MBI</text></svg>
        </svg>
	<a class="navbar-brand" href="/">Dashboard</a>
	<div class="collapse navbar-collapse" id="navbarsExampleDefault"></div>
      </div>
    </nav>
    <main class='container'>

<h2>Version report</h2>
<p>Based on data fetched at {{.Time}} by <code>{{.Hostname}}</code></p>

<table class="version-dashboard table table-bordered table-striped table-hover">
  <thead class="table-primary">
    <tr>
      <th rowspan="2">Package name</th>
      <th rowspan="2">Javapackages<br/>Bootstrap<br/>version</th>
      <th colspan="{{ len .Columns.Fedora }}">Fedora versions</th>
      <th colspan="2">Upstream version</th>
    </tr>
    <tr>
      {{ range .Columns.Fedora }}
      <th>{{.}}</th>
      {{ end }}
      <th>Stable</th>
      <th>Latest</th>
    </tr>
  </thead>
  <tbody>
    {{ range $component, $_ := .Versions }}
    <tr>
      <td><code>{{$component}}</code></td>

      <td>{{.JpbNorm.Version}}</td>

      {{ range .Normalized }}
      <td colspan="{{.Repeat}}">{{.Version}}</td>
      {{ end }}

      {{ if eq .Upstream.Latest .Upstream.Stable }}
      <td colspan="2">{{.Upstream.Latest}}</td>
      {{ else }}
      <td>{{.Upstream.Stable}}</td>
      <td>{{.Upstream.Latest}}</td>
      {{ end }}
    </tr>
    {{ end }}
  </tbody>
</table>

    </main>
    <script src="https://mbi-artifacts.s3.eu-central-1.amazonaws.com/static/bootstrap/js/bootstrap.bundle.min.js"></script>
  </body>
</html>
`))
