package v1

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestSubjectIdentityRoundTrip(t *testing.T) {
	encoded, err := EncodeSubject("nakamadevs", "5f5aeb53-9ec9-4f26-bc9f-6243ac77e75a")
	require.NoError(t, err)
	require.Equal(t, "user:nakamadevs|5f5aeb53-9ec9-4f26-bc9f-6243ac77e75a", encoded)

	realmID, subject, err := DecodeSubject(encoded)
	require.NoError(t, err)
	require.Equal(t, "nakamadevs", realmID)
	require.Equal(t, "5f5aeb53-9ec9-4f26-bc9f-6243ac77e75a", subject)
}

func TestOrganizationIdentityRoundTrip(t *testing.T) {
	encoded, err := EncodeOrganization("nakamadevs", "acme")
	require.NoError(t, err)
	require.Equal(t, "organization:nakamadevs|acme", encoded)

	realmID, organizationID, err := DecodeOrganization(encoded)
	require.NoError(t, err)
	require.Equal(t, "nakamadevs", realmID)
	require.Equal(t, "acme", organizationID)
}

func TestIdentityEncodingRejectsAmbiguousOrUnsafeComponents(t *testing.T) {
	tests := []struct {
		name    string
		realmID string
		value   string
	}{
		{name: "separator in realm", realmID: "nakama|devs", value: "subject"},
		{name: "separator in value", realmID: "nakamadevs", value: "subject|value"},
		{name: "colon in realm", realmID: "nakama:devs", value: "subject"},
		{name: "colon in value", realmID: "nakamadevs", value: "subject:value"},
		{name: "empty realm", realmID: "", value: "subject"},
		{name: "empty value", realmID: "nakamadevs", value: ""},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			_, err := EncodeSubject(test.realmID, test.value)
			require.Error(t, err)
		})
	}
}

func TestIdentityDecodingRejectsCollisions(t *testing.T) {
	for _, value := range []string{
		"user:nakamadevs|subject|suffix",
		"user:nakama:devs|subject",
		"user:nakamadevs|subject:value",
		"user:nakamadevs|",
		"organization:nakamadevs|subject",
	} {
		t.Run(value, func(t *testing.T) {
			_, _, err := DecodeSubject(value)
			require.Error(t, err)
		})
	}
}
