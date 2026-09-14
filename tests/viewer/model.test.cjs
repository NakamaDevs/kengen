const test = require('node:test');
const assert = require('node:assert/strict');
const model = require('../../internal/viewer/web/model.js');

test('renders nested union, intersection, exclusion and parent inheritance without losing grouping', () => {
 const rewrite = {intersection:{child:[{union:{child:[{computedUserset:{relation:'owner'}},{tupleToUserset:{tupleset:{relation:'parent'},computedUserset:{relation:'viewer'}}}]}},{difference:{base:{this:{}},subtract:{computedUserset:{relation:'blocked'}}}}]}};
 assert.equal(model.expression(rewrite, [{type:'user',wildcard:{}},{type:'group',relation:'member',condition:'active'}]), '((owner or viewer from parent) and ([user:*, group#member with active] but not blocked))');
});
test('extracts type links including usersets and conditional restrictions', () => {
 const links=model.links({type_definitions:[{type:'document',metadata:{relations:{viewer:{directly_related_user_types:[{type:'group',relation:'member',condition:'active'}]}}}}]});
 assert.deepEqual(links,[{source:'document',target:'group',relation:'viewer',label:'group#member with active'}]);
});
test('unknown rewrites stay explicit instead of appearing to grant access', () => {
 assert.equal(model.expression({futureRewrite:{}}, []), 'Unsupported expression — inspect JSON');
});
