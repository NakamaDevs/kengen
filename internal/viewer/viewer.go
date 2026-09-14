// Package viewer serves the optional Kengen tuple viewer without changing API routes.
package viewer

import (
	"embed"
	"net/http"
)

//go:embed web/*
var files embed.FS

// NewHandler serves the viewer's static resources and delegates all API requests.
// Authentication remains with the API. No server credentials enter these resources.
func NewHandler(api http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		name, contentType := "", ""
		switch r.URL.Path {
		case "/":
			name, contentType = "index.html", "text/html; charset=utf-8"
		case "/viewer/model.js":
			name, contentType = "model.js", "text/javascript; charset=utf-8"
		case "/viewer/app.js":
			name, contentType = "app.js", "text/javascript; charset=utf-8"
		case "/viewer/styles.css":
			name, contentType = "styles.css", "text/css; charset=utf-8"
		}
		if name == "" || (r.Method != http.MethodGet && r.Method != http.MethodHead) {
			api.ServeHTTP(w, r)
			return
		}
		body, err := files.ReadFile("web/" + name)
		if err != nil {
			http.Error(w, "Viewer asset unavailable", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", contentType)
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
		if r.Method == http.MethodGet {
			_, _ = w.Write(body)
		}
	})
}
