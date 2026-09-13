package run

import (
	"testing"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
	"github.com/stretchr/testify/require"

	"github.com/openfga/openfga/cmd"
	"github.com/openfga/openfga/cmd/util"
)

func TestServiceIdentityConfig(t *testing.T) {
	for _, source := range []string{"default", "flag", "environment", "file"} {
		t.Run(source, func(t *testing.T) {
			viper.Reset()
			t.Cleanup(viper.Reset)
			if source == "file" {
				util.PrepareTempConfigFile(t, "authn:\n  oidc:\n    allowedClientIDs: [service-old, service-new]\n")
			} else {
				util.PrepareTempConfigDir(t)
			}
			if source == "environment" {
				t.Setenv("OPENFGA_AUTHN_OIDC_ALLOWED_CLIENT_IDS", "service-old,service-new")
			}
			runCmd := NewRunCommand()
			runCmd.RunE = func(_ *cobra.Command, _ []string) error { return nil }
			root := cmd.NewRootCommand()
			root.AddCommand(runCmd)
			args := []string{"run"}
			if source == "flag" {
				args = append(args, "--authn-oidc-allowed-client-ids=service-old,service-new")
			}
			root.SetArgs(args)
			require.NoError(t, root.Execute())
			cfg, err := ReadConfig()
			require.NoError(t, err)
			if source == "default" {
				require.Empty(t, cfg.Authn.AllowedClientIDs)
			} else {
				require.Equal(t, []string{"service-old", "service-new"}, cfg.Authn.AllowedClientIDs)
			}
		})
	}
}
