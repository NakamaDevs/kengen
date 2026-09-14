package viewer

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestViewerAndAPIRouting(t *testing.T) {
	api := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-API-Authorization", r.Header.Get("Authorization"))
		w.WriteHeader(http.StatusUnauthorized)
	})
	handler := NewHandler(api)
	for _, path := range []string{"/", "/viewer/app.js", "/viewer/styles.css"} {
		r := httptest.NewRecorder()
		handler.ServeHTTP(r, httptest.NewRequest(http.MethodGet, path, nil))
		require.Equal(t, http.StatusOK, r.Code)
		require.NotEmpty(t, r.Body.String())
		require.Contains(t, r.Header().Get("Content-Security-Policy"), "connect-src 'self'")
		require.Equal(t, "no-store", r.Header().Get("Cache-Control"))
	}
	for _, path := range []string{"/stores", "/stores/example/read", "/healthz", "/viewer/missing", "/unknown"} {
		r := httptest.NewRecorder()
		request := httptest.NewRequest(http.MethodPost, path, nil)
		request.Header.Set("Authorization", "Bearer test-only")
		handler.ServeHTTP(r, request)
		require.Equal(t, http.StatusUnauthorized, r.Code, path)
		require.Equal(t, "Bearer test-only", r.Header().Get("X-API-Authorization"))
	}
}

func TestViewerHeadAndNonGETRoot(t *testing.T) {
	handler := NewHandler(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	r := httptest.NewRecorder()
	handler.ServeHTTP(r, httptest.NewRequest(http.MethodHead, "/", nil))
	require.Equal(t, http.StatusOK, r.Code)
	require.Empty(t, r.Body.String())
	r = httptest.NewRecorder()
	handler.ServeHTTP(r, httptest.NewRequest(http.MethodPost, "/", nil))
	require.Equal(t, http.StatusNotFound, r.Code)
}
