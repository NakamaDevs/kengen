package oidc

import (
	"testing"
	"time"

	jwt "github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/require"
)

// NakamaDevs integration (NAK-908): restrict service tokens without changing the default policy.
func TestServiceIdentity(t *testing.T) {
	originalFetch := fetchJWKs
	t.Cleanup(func() { fetchJWKs = originalFetch })
	for _, tc := range []struct {
		name     string
		change   jwt.MapClaims
		clients  []string
		subjects []string
		allowed  bool
	}{
		{name: "service", allowed: true},
		{name: "wrong_issuer", change: jwt.MapClaims{"iss": "https://other.example"}},
		{name: "missing_issuer", change: jwt.MapClaims{"iss": nil}},
		{name: "wrong_audience", change: jwt.MapClaims{"aud": "browser"}},
		{name: "missing_audience", change: jwt.MapClaims{"aud": nil}},
		{name: "user_subject", change: jwt.MapClaims{"sub": "user-sub"}},
		{name: "missing_subject", change: jwt.MapClaims{"sub": nil}},
		{name: "browser_client", change: jwt.MapClaims{"azp": "keikaku"}},
		{name: "admin_client", change: jwt.MapClaims{"azp": "kengen-admin"}},
		{name: "missing_client", change: jwt.MapClaims{"azp": nil}},
		{name: "empty_client", change: jwt.MapClaims{"azp": ""}},
		{name: "non_string_client", change: jwt.MapClaims{"azp": []string{"keikaku-kengen"}}},
		{name: "fallback_does_not_replace_azp", change: jwt.MapClaims{"azp": nil, "client_id": "keikaku-kengen"}},
		{name: "rotation_old", clients: []string{"keikaku-kengen", "keikaku-kengen-next"}, subjects: []string{"service-sub", "next-sub"}, allowed: true},
		{name: "rotation_new", change: jwt.MapClaims{"azp": "keikaku-kengen-next", "sub": "next-sub"}, clients: []string{"keikaku-kengen", "keikaku-kengen-next"}, subjects: []string{"service-sub", "next-sub"}, allowed: true},
		{name: "revoked_subject", subjects: []string{"next-sub"}},
		{name: "revoked_client", clients: []string{"keikaku-kengen-next"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			claims := jwt.MapClaims{"iss": "https://issuer.example", "aud": "kengen", "sub": "service-sub", "azp": "keikaku-kengen", "exp": time.Now().Add(time.Minute).Unix()}
			for k, v := range tc.change {
				if v == nil {
					delete(claims, k)
				} else {
					claims[k] = v
				}
			}
			if tc.subjects == nil {
				tc.subjects = []string{"service-sub"}
			}
			if tc.clients == nil {
				tc.clients = []string{"keikaku-kengen"}
			}
			a, ctx, _, err := quickConfigSetup(Config{jwkKid: "service", jwtKid: "service", issuerURL: "https://issuer.example", audience: "kengen", subjects: tc.subjects, clientIDClaims: []string{"azp"}, allowedClientIDs: tc.clients, jwtClaims: claims})
			require.NoError(t, err)
			principal, err := a.Authenticate(ctx)
			if tc.allowed {
				require.NoError(t, err)
				require.NotNil(t, principal)
			} else {
				require.ErrorIs(t, err, errInvalidClaims)
				require.Nil(t, principal)
			}
		})
	}
}
