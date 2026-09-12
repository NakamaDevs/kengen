package v1_test

import (
	"context"
	"fmt"
	"os"
	"testing"

	"github.com/stretchr/testify/require"

	openfgav1 "github.com/openfga/api/proto/openfga/v1"
	parser "github.com/openfga/language/pkg/go/transformer"

	nakamadevsmodel "github.com/openfga/openfga/models/nakamadevs/v1"
	"github.com/openfga/openfga/pkg/typesystem"
	"github.com/openfga/openfga/tests"
)

func loadModel(t *testing.T) *openfgav1.AuthorizationModel {
	t.Helper()

	contents, err := os.ReadFile("model.fga")
	require.NoError(t, err)

	model := parser.MustTransformDSLToProto(string(contents))
	_, err = typesystem.NewAndValidate(context.Background(), model)
	require.NoError(t, err)

	return model
}

func TestModelIsValid(t *testing.T) {
	loadModel(t)
}

func subject(t *testing.T, subjectID string) string {
	t.Helper()

	value, err := nakamadevsmodel.EncodeSubject("nakamadevs", subjectID)
	require.NoError(t, err)

	return value
}

func organization(t *testing.T, organizationID string) string {
	t.Helper()

	value, err := nakamadevsmodel.EncodeOrganization("nakamadevs", organizationID)
	require.NoError(t, err)

	return value
}

func TestAuthorizations(t *testing.T) {
	client := tests.BuildClientInterface(t, "memory", nil)
	ctx := context.Background()
	model := loadModel(t)
	owner := subject(t, "5f5aeb53-9ec9-4f26-bc9f-6243ac77e75a")
	commenter := subject(t, "3f562fed-a84d-40e2-9170-f81f5e32aa71")
	organizationViewer := subject(t, "ef8ced67-2e4d-4a81-b1a2-a4a7448b5ab1")
	parentEditor := subject(t, "4db18b3d-6b44-4463-8bd3-124528fd56c3")
	directViewer := subject(t, "91f1fb10-25a2-4e13-bd02-c5aa71271f09")
	otherOwner := subject(t, "1ed0edeb-0b4e-4baa-a572-6a6d2cfafefe")
	anonymous := subject(t, "anonymous")
	unrelated := subject(t, "3a8b468b-edb5-453b-a22f-ef5ae5075e8a")
	acme := organization(t, "acme")
	public := organization(t, "public")
	other := organization(t, "other")

	store, err := client.CreateStore(ctx, &openfgav1.CreateStoreRequest{Name: "nakamadevs-model-v1"})
	require.NoError(t, err)

	writtenModel, err := client.WriteAuthorizationModel(ctx, &openfgav1.WriteAuthorizationModelRequest{
		StoreId:         store.GetId(),
		SchemaVersion:   model.GetSchemaVersion(),
		TypeDefinitions: model.GetTypeDefinitions(),
	})
	require.NoError(t, err)

	_, err = client.Write(ctx, &openfgav1.WriteRequest{
		StoreId:              store.GetId(),
		AuthorizationModelId: writtenModel.GetAuthorizationModelId(),
		Writes: &openfgav1.WriteRequestWrites{TupleKeys: []*openfgav1.TupleKey{
			{Object: acme, Relation: "owner", User: owner},
			{Object: acme, Relation: "commenter", User: commenter},
			{Object: acme, Relation: "viewer", User: organizationViewer},
			{Object: public, Relation: "viewer", User: "user:*"},
			{Object: other, Relation: "owner", User: otherOwner},
			{Object: "keikaku_node:root", Relation: "organization", User: acme},
			{Object: "keikaku_node:root", Relation: "editor", User: parentEditor},
			{Object: "keikaku_node:child", Relation: "parent", User: "keikaku_node:root"},
			{Object: "keikaku_node:child", Relation: "viewer", User: directViewer},
			{Object: "keikaku_node:sibling", Relation: "parent", User: "keikaku_node:root"},
			{Object: "keikaku_node:other-root", Relation: "organization", User: other},
			{Object: "keikaku_node:public-root", Relation: "organization", User: public},
			{Object: "keikaku_node:public-child", Relation: "parent", User: "keikaku_node:public-root"},
			{Object: "article:guide", Relation: "organization", User: acme},
			{Object: "article:public", Relation: "organization", User: public},
		}},
	})
	require.NoError(t, err)

	tests := []struct {
		name     string
		user     string
		relation string
		object   string
		allowed  bool
	}{
		{name: "owner inherits every role", user: owner, relation: "owner", object: "keikaku_node:child", allowed: true},
		{name: "owner administers child", user: owner, relation: "administrator", object: "keikaku_node:child", allowed: true},
		{name: "owner edits child", user: owner, relation: "editor", object: "keikaku_node:child", allowed: true},
		{name: "owner comments on child", user: owner, relation: "commenter", object: "keikaku_node:child", allowed: true},
		{name: "owner views child", user: owner, relation: "viewer", object: "keikaku_node:child", allowed: true},
		{name: "organization commenter inherits to child", user: commenter, relation: "commenter", object: "keikaku_node:child", allowed: true},
		{name: "organization commenter views child", user: commenter, relation: "viewer", object: "keikaku_node:child", allowed: true},
		{name: "organization commenter cannot edit child", user: commenter, relation: "editor", object: "keikaku_node:child", allowed: false},
		{name: "direct parent editor inherits to child", user: parentEditor, relation: "editor", object: "keikaku_node:child", allowed: true},
		{name: "direct parent editor comments on child", user: parentEditor, relation: "commenter", object: "keikaku_node:child", allowed: true},
		{name: "direct parent editor cannot administer child", user: parentEditor, relation: "administrator", object: "keikaku_node:child", allowed: false},
		{name: "direct node viewer can view", user: directViewer, relation: "viewer", object: "keikaku_node:child", allowed: true},
		{name: "direct node viewer cannot comment", user: directViewer, relation: "commenter", object: "keikaku_node:child", allowed: false},
		{name: "direct node viewer cannot view sibling", user: directViewer, relation: "viewer", object: "keikaku_node:sibling", allowed: false},
		{name: "direct organization viewer reaches child", user: organizationViewer, relation: "viewer", object: "keikaku_node:child", allowed: true},
		{name: "public reader views a descendant", user: anonymous, relation: "viewer", object: "keikaku_node:public-child", allowed: true},
		{name: "public reader cannot comment", user: anonymous, relation: "commenter", object: "keikaku_node:public-child", allowed: false},
		{name: "acme owner can view acme article", user: owner, relation: "viewer", object: "article:guide", allowed: true},
		{name: "node editor cannot view article", user: parentEditor, relation: "viewer", object: "article:guide", allowed: false},
		{name: "public reader views article", user: anonymous, relation: "viewer", object: "article:public", allowed: true},
		{name: "public reader cannot comment on article", user: anonymous, relation: "commenter", object: "article:public", allowed: false},
		{name: "public reader cannot edit article", user: anonymous, relation: "editor", object: "article:public", allowed: false},
		{name: "acme owner cannot view other organization", user: owner, relation: "viewer", object: "keikaku_node:other-root", allowed: false},
		{name: "other organization owner cannot view acme node", user: otherOwner, relation: "viewer", object: "keikaku_node:child", allowed: false},
		{name: "unrelated user is denied", user: unrelated, relation: "viewer", object: "keikaku_node:child", allowed: false},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			response, err := client.Check(ctx, &openfgav1.CheckRequest{
				StoreId:              store.GetId(),
				AuthorizationModelId: writtenModel.GetAuthorizationModelId(),
				TupleKey: &openfgav1.CheckRequestTupleKey{
					User:     test.user,
					Relation: test.relation,
					Object:   test.object,
				},
			})
			require.NoError(t, err)
			require.Equal(t, test.allowed, response.GetAllowed())
		})
	}
}

func TestRoleGrantsAcrossProductTypes(t *testing.T) {
	client := tests.BuildClientInterface(t, "memory", nil)
	ctx := context.Background()
	model := loadModel(t)
	acme := organization(t, "acme")

	store, err := client.CreateStore(ctx, &openfgav1.CreateStoreRequest{Name: "nakamadevs-role-matrix-v1"})
	require.NoError(t, err)

	writtenModel, err := client.WriteAuthorizationModel(ctx, &openfgav1.WriteAuthorizationModelRequest{
		StoreId:         store.GetId(),
		SchemaVersion:   model.GetSchemaVersion(),
		TypeDefinitions: model.GetTypeDefinitions(),
	})
	require.NoError(t, err)

	roles := []string{"owner", "administrator", "editor", "commenter", "viewer"}
	products := []string{"keikaku_node", "article"}
	tuples := make([]*openfgav1.TupleKey, 0, len(products)*(1+len(roles)*4))
	assertions := make([]authorizationAssertion, 0, len(products)*len(roles)*len(roles)*3)

	for _, product := range products {
		tuples = append(tuples, &openfgav1.TupleKey{
			Object:   product + ":organization-root",
			Relation: "organization",
			User:     acme,
		})

		for roleIndex, role := range roles {
			organizationUser := subject(t, fmt.Sprintf("%s-organization-%s", product, role))
			directUser := subject(t, fmt.Sprintf("%s-direct-%s", product, role))
			parentUser := subject(t, fmt.Sprintf("%s-parent-%s", product, role))
			parent := product + ":parent-" + role
			child := product + ":child-" + role
			direct := product + ":direct-" + role

			tuples = append(tuples,
				&openfgav1.TupleKey{Object: acme, Relation: role, User: organizationUser},
				&openfgav1.TupleKey{Object: direct, Relation: role, User: directUser},
				&openfgav1.TupleKey{Object: parent, Relation: role, User: parentUser},
				&openfgav1.TupleKey{Object: child, Relation: "parent", User: parent},
			)

			for relationIndex, relation := range roles {
				allowed := relationIndex >= roleIndex
				assertions = append(assertions,
					authorizationAssertion{
						name:     fmt.Sprintf("organization %s grants %s", role, relation),
						user:     organizationUser,
						relation: relation,
						object:   acme,
						allowed:  allowed,
					},
					authorizationAssertion{
						name:     fmt.Sprintf("%s inherits organization %s as %s", product, role, relation),
						user:     organizationUser,
						relation: relation,
						object:   product + ":organization-root",
						allowed:  allowed,
					},
					authorizationAssertion{
						name:     fmt.Sprintf("%s direct %s grants %s", product, role, relation),
						user:     directUser,
						relation: relation,
						object:   direct,
						allowed:  allowed,
					},
					authorizationAssertion{
						name:     fmt.Sprintf("%s parent %s grants %s", product, role, relation),
						user:     parentUser,
						relation: relation,
						object:   child,
						allowed:  allowed,
					},
				)
			}
		}
	}

	_, err = client.Write(ctx, &openfgav1.WriteRequest{
		StoreId:              store.GetId(),
		AuthorizationModelId: writtenModel.GetAuthorizationModelId(),
		Writes:               &openfgav1.WriteRequestWrites{TupleKeys: tuples},
	})
	require.NoError(t, err)

	for _, assertion := range assertions {
		t.Run(assertion.name, func(t *testing.T) {
			response, err := client.Check(ctx, &openfgav1.CheckRequest{
				StoreId:              store.GetId(),
				AuthorizationModelId: writtenModel.GetAuthorizationModelId(),
				TupleKey: &openfgav1.CheckRequestTupleKey{
					User:     assertion.user,
					Relation: assertion.relation,
					Object:   assertion.object,
				},
			})
			require.NoError(t, err)
			require.Equal(t, assertion.allowed, response.GetAllowed())
		})
	}
}

type authorizationAssertion struct {
	name     string
	user     string
	relation string
	object   string
	allowed  bool
}
