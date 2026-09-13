package dokploy_test

import (
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
	"gopkg.in/yaml.v3"
)

const (
	productionComposePath = "production.compose.yaml"
	kengenImage           = "${KENGEN_IMAGE_DIGEST:?KENGEN_IMAGE_DIGEST must be an immutable image digest}"
	oidcIssuer            = "${KENGEN_OIDC_ISSUER:?KENGEN_OIDC_ISSUER must be an HTTPS issuer URL}"
	oidcAudience          = "${KENGEN_OIDC_AUDIENCE:?KENGEN_OIDC_AUDIENCE must be set}"
	oidcSubjects          = "${KENGEN_OIDC_SUBJECTS:?KENGEN_OIDC_SUBJECTS must be set}"
	postgresImage         = "postgres:17.9@sha256:2a0d0fe14825b0939f78a8cad5cd4e6aa68bf94d0e5dd96e24b6d23af4315545"
	postgresPassword      = "${KENGEN_POSTGRES_PASSWORD:?KENGEN_POSTGRES_PASSWORD must be set}"
)

type compose struct {
	Services map[string]service `yaml:"services"`
	Volumes  map[string]any     `yaml:"volumes"`
}

type service struct {
	Image       string            `yaml:"image"`
	Command     []string          `yaml:"command"`
	Environment map[string]string `yaml:"environment"`
	DependsOn   map[string]any    `yaml:"depends_on"`
	Expose      []string          `yaml:"expose"`
	Ports       []string          `yaml:"ports"`
	Restart     string            `yaml:"restart"`
	Volumes     []string          `yaml:"volumes"`
}

func loadProductionCompose(t *testing.T) (compose, string) {
	t.Helper()

	path := filepath.Join(productionComposePath)
	contents, err := os.ReadFile(path)
	require.NoError(t, err)

	var deployment compose
	require.NoError(t, yaml.Unmarshal(contents, &deployment))

	return deployment, string(contents)
}

func TestProductionCompose_UsesImmutableImagesAndPersistentPostgres(t *testing.T) {
	deployment, _ := loadProductionCompose(t)

	require.Equal(t, []string{"kengen", "migrate", "postgres"}, sortedServiceNames(deployment.Services))
	require.Equal(t, kengenImage, deployment.Services["kengen"].Image)
	require.Equal(t, deployment.Services["kengen"].Image, deployment.Services["migrate"].Image)
	require.Equal(t, postgresImage, deployment.Services["postgres"].Image)
	require.Contains(t, deployment.Services["postgres"].Volumes, "kengen-postgres:/var/lib/postgresql/data")
	require.Contains(t, deployment.Volumes, "kengen-postgres")
}

func TestProductionCompose_MigratesBeforeStartingTheService(t *testing.T) {
	deployment, _ := loadProductionCompose(t)

	migrate := deployment.Services["migrate"]
	require.Equal(t, []string{"migrate"}, migrate.Command)
	require.Equal(t, "no", migrate.Restart)
	require.Equal(t, "service_healthy", dependsOnCondition(t, migrate.DependsOn, "postgres"))

	kengen := deployment.Services["kengen"]
	require.Equal(t, []string{"run"}, kengen.Command)
	require.Equal(t, "service_completed_successfully", dependsOnCondition(t, kengen.DependsOn, "migrate"))
}

func TestProductionCompose_FailsClosedAndDoesNotPublishPrivateSurfaces(t *testing.T) {
	deployment, contents := loadProductionCompose(t)

	for name, service := range deployment.Services {
		require.Emptyf(t, service.Ports, "%s must not publish a host port", name)
	}

	kengen := deployment.Services["kengen"]
	require.Equal(t, []string{"8080"}, kengen.Expose)
	require.Equal(t, "oidc", kengen.Environment["OPENFGA_AUTHN_METHOD"])
	require.Equal(t, oidcIssuer, kengen.Environment["OPENFGA_AUTHN_OIDC_ISSUER"])
	require.Equal(t, oidcAudience, kengen.Environment["OPENFGA_AUTHN_OIDC_AUDIENCE"])
	require.Equal(t, oidcSubjects, kengen.Environment["OPENFGA_AUTHN_OIDC_SUBJECTS"])
	require.Equal(t, "false", kengen.Environment["OPENFGA_PLAYGROUND_ENABLED"])
	require.Equal(t, "false", kengen.Environment["OPENFGA_METRICS_ENABLED"])
	require.Equal(t, "false", kengen.Environment["OPENFGA_PROFILER_ENABLED"])
	require.Equal(t, postgresPassword, kengen.Environment["OPENFGA_DATASTORE_PASSWORD"])
	require.NotContains(t, contents, "OPENFGA_AUTHN_METHOD=none")
}

func sortedServiceNames(services map[string]service) []string {
	names := make([]string, 0, len(services))
	for name := range services {
		names = append(names, name)
	}

	sort.Strings(names)

	return names
}

func dependsOnCondition(t *testing.T, dependsOn map[string]any, serviceName string) string {
	t.Helper()

	dependency, ok := dependsOn[serviceName].(map[string]any)
	require.Truef(t, ok, "%s dependency must have a condition", serviceName)

	condition, ok := dependency["condition"].(string)
	require.Truef(t, ok, "%s dependency condition must be a string", serviceName)

	return condition
}

func TestProductionCompose_ReferencesSecretsByNameOnly(t *testing.T) {
	_, contents := loadProductionCompose(t)

	for _, secret := range []string{"KENGEN_POSTGRES_PASSWORD"} {
		require.Contains(t, contents, "${"+secret+":?")
	}
	require.NotContains(t, strings.ToLower(contents), "password=postgres")
}

func TestProductionValidation_RejectsNonHTTPSOIDCIssuer(t *testing.T) {
	command := productionValidation("http://keycloak.example.com/realms/kengen", "kengen-service")

	output, err := command.CombinedOutput()
	require.Error(t, err)
	require.Contains(t, string(output), "KENGEN_OIDC_ISSUER must start with https://")
}

func TestProductionValidation_ValidatesCommaSeparatedOIDCSubjects(t *testing.T) {
	valid := productionValidation("https://keycloak.example.com/realms/kengen", "old-sub,new-sub")
	validOutput, validErr := valid.CombinedOutput()
	require.NoError(t, validErr, string(validOutput))

	invalid := productionValidation("https://keycloak.example.com/realms/kengen", "old-sub new-sub")
	invalidOutput, invalidErr := invalid.CombinedOutput()
	require.Error(t, invalidErr)
	require.Contains(t, string(invalidOutput), "comma-separated list without whitespace")
}

func productionValidation(issuer, subjects string) *exec.Cmd {
	command := exec.Command("sh", "validate-production.sh", "--validate-only")
	command.Env = append(os.Environ(),
		"KENGEN_IMAGE_DIGEST=ghcr.io/nakamadevs/kengen@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		"KENGEN_OIDC_ISSUER="+issuer,
		"KENGEN_OIDC_AUDIENCE=kengen-api",
		"KENGEN_OIDC_SUBJECTS="+subjects,
		"KENGEN_POSTGRES_PASSWORD=validation-password",
	)

	return command
}
