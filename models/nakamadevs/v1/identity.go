// Package v1 defines the NakamaDevs v1 OpenFGA model boundary.
package v1

import (
	"fmt"
	"strings"

	"github.com/openfga/openfga/pkg/tuple"
)

const subjectType = "user"
const organizationType = "organization"

// EncodeSubject converts Keycloak realm and subject identifiers into an OpenFGA user.
func EncodeSubject(realmID, subject string) (string, error) {
	return encode(subjectType, realmID, subject)
}

// DecodeSubject converts an OpenFGA user into Keycloak realm and subject identifiers.
func DecodeSubject(value string) (string, string, error) {
	return decode(subjectType, value)
}

// EncodeOrganization converts Keycloak realm and organization identifiers into an OpenFGA organization.
func EncodeOrganization(realmID, organizationID string) (string, error) {
	return encode(organizationType, realmID, organizationID)
}

// DecodeOrganization converts an OpenFGA organization into Keycloak realm and organization identifiers.
func DecodeOrganization(value string) (string, string, error) {
	return decode(organizationType, value)
}

func encode(objectType, realmID, value string) (string, error) {
	if err := validateComponent("realm ID", realmID); err != nil {
		return "", err
	}

	if err := validateComponent("identifier", value); err != nil {
		return "", err
	}

	return objectType + ":" + realmID + "|" + value, nil
}

func decode(objectType, value string) (string, string, error) {
	prefix := objectType + ":"
	if !strings.HasPrefix(value, prefix) {
		return "", "", fmt.Errorf("identifier must start with %q", prefix)
	}

	realmID, identifier, found := strings.Cut(strings.TrimPrefix(value, prefix), "|")
	if !found || strings.Contains(identifier, "|") {
		return "", "", fmt.Errorf("identifier must contain one separator")
	}

	if err := validateComponent("realm ID", realmID); err != nil {
		return "", "", err
	}

	if err := validateComponent("identifier", identifier); err != nil {
		return "", "", err
	}

	return realmID, identifier, nil
}

func validateComponent(name, value string) error {
	if strings.Contains(value, "|") {
		return fmt.Errorf("%s must not contain the separator", name)
	}

	if !tuple.IsValidUserID(value) {
		return fmt.Errorf("%s is not OpenFGA-safe", name)
	}

	return nil
}
