/* Read-only visualization of OpenFGA model definitions. No API calls or credentials. */
(function (root) {
  'use strict';
  function restriction(ref) {
    return ref.type + (ref.relation ? '#' + ref.relation : ref.wildcard ? ':*' : '') +
      (ref.condition ? ' with ' + ref.condition : '');
  }
  function expression(rule, allowed = [], depth = 0) {
    if (!rule || depth > 40) return 'Unsupported expression — inspect JSON';
    if (Object.hasOwn(rule, 'this')) return allowed.length ? '[' + allowed.map(restriction).join(', ') + ']' : 'direct assignment (type restrictions unavailable)';
    const computed = rule.computedUserset || rule.computed_userset;
    if (computed) return computed.relation;
    const parent = rule.tupleToUserset || rule.tuple_to_userset;
    if (parent) return (parent.computedUserset || parent.computed_userset)?.relation + ' from ' + parent.tupleset?.relation;
    for (const [field, operator] of [['union', 'or'], ['intersection', 'and']]) {
      if (rule[field]?.child?.length) return '(' + rule[field].child.map(child => expression(child, allowed, depth + 1)).join(' ' + operator + ' ') + ')';
    }
    if (rule.difference) return '(' + expression(rule.difference.base, allowed, depth + 1) + ' but not ' + expression(rule.difference.subtract, allowed, depth + 1) + ')';
    return 'Unsupported expression — inspect JSON';
  }
  function links(model) {
    const result = [];
    for (const type of model.type_definitions || []) {
      for (const [relation, metadata] of Object.entries(type.metadata?.relations || {})) {
        for (const ref of metadata.directly_related_user_types || []) {
          result.push({source: type.type, target: ref.type, relation, label: restriction(ref)});
        }
      }
    }
    return result;
  }
  function render(container, model) {
    container.replaceChildren();
    if (!model) return;
    const types = model.type_definitions || [];
    if (!types.length) return;
    let selected = types.find(type => Object.keys(type.relations || {}).length)?.type || types[0].type;
    const element = (tag, text, className) => {
      const node = document.createElement(tag);
      if (text !== undefined) node.textContent = text;
      if (className) node.className = className;
      return node;
    };
    const heading = element('div', undefined, 'model-map-heading');
    heading.append(element('h2', 'Model map'), element('span', types.length + ' object types', 'small muted'));
    container.append(heading, element('p', 'Select a type to inspect its relations. Arrows point to the types accepted by a direct relation.', 'small muted'));
    const selectorLabel = element('label', 'Object type');
    const selector = element('select'); selector.id = 'model-type'; selectorLabel.htmlFor = selector.id;
    for (const type of types) { const option = element('option', type.type); option.value = type.type; selector.append(option); }
    selector.value = selected;
    const controls = element('div', undefined, 'model-controls'); controls.append(selectorLabel, selector); container.append(controls);
    const graph = element('div', undefined, 'model-graph');
    graph.tabIndex = 0; graph.setAttribute('aria-label', 'Scrollable object type map');
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const columns = Math.min(types.length, 3), rows = Math.ceil(types.length / columns);
    svg.setAttribute('viewBox', `0 0 ${columns * 310 + 40} ${rows * 160 + 30}`);
    svg.setAttribute('width', String(columns * 310 + 40)); svg.setAttribute('height', String(rows * 160 + 30));
    svg.setAttribute('role', 'group'); svg.setAttribute('aria-label', 'Authorization model object types');
    function shape(tag, attrs, text) {
      const node = document.createElementNS(svg.namespaceURI, tag);
      for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
      if (text !== undefined) node.textContent = text;
      return node;
    }
    const defs = shape('defs', {}), marker = shape('marker', {id:'model-arrow', viewBox:'0 0 10 10', refX:9, refY:5, markerWidth:7, markerHeight:7, orient:'auto-start-reverse'});
    marker.append(shape('path', {d:'M 0 0 L 10 5 L 0 10 z', class:'model-arrow'})); defs.append(marker); svg.append(defs);
    const positions = new Map(types.map((type, index) => [type.type, {x:30 + (index % columns) * 310, y:35 + Math.floor(index / columns) * 160}]));
    const edges = [], nodes = [];
    const grouped = new Map();
    for (const link of links(model)) {
      const key = JSON.stringify([link.source, link.target]);
      if (!grouped.has(key)) grouped.set(key, {...link, relations: new Set()});
      grouped.get(key).relations.add(link.relation);
    }
    for (const link of grouped.values()) {
      const from = positions.get(link.source), to = positions.get(link.target);
      if (!from || !to) continue;
      const x1 = from.x + 240, y1 = from.y + 40, x2 = to.x, y2 = to.y + 40;
      const path = link.source === link.target
        ? `M ${from.x + 80} ${from.y} C ${from.x + 60} ${from.y - 32}, ${from.x + 190} ${from.y - 32}, ${from.x + 170} ${from.y}`
        : `M ${x1} ${y1} C ${x1 + 45} ${y1 + 75}, ${x2 - 45} ${y2 + 75}, ${x2} ${y2}`;
      const edge = shape('path', {d:path, class:'model-edge', 'marker-end':'url(#model-arrow)'});
      edge.append(shape('title', {}, link.source + ' → ' + link.target + ': ' + [...link.relations].join(', ')));
      svg.append(edge); edges.push({edge, link});
    }
    for (const type of types) {
      const p = positions.get(type.type), node = shape('g', {class:'model-node', tabindex:0, role:'button', 'aria-label':'Inspect ' + type.type});
      node.append(shape('rect', {x:p.x, y:p.y, width:240, height:80, rx:10}));
      node.append(shape('text', {x:p.x + 18, y:p.y + 32, class:'model-node-name'}, type.type.length > 25 ? type.type.slice(0, 23) + '…' : type.type));
      node.append(shape('text', {x:p.x + 18, y:p.y + 57, class:'model-node-count'}, Object.keys(type.relations || {}).length + ' relations'));
      node.append(shape('title', {}, type.type));
      node.addEventListener('click', () => choose(type.type));
      node.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(type.type); } });
      svg.append(node); nodes.push({node, type});
    }
    graph.append(svg); container.append(graph);
    const detail = element('section', undefined, 'model-relations'); detail.setAttribute('aria-live', 'polite'); container.append(detail);
    function choose(name) {
      selected = name; selector.value = name;
      for (const {node, type} of nodes) node.setAttribute('aria-pressed', String(type.type === selected));
      for (const {edge, link} of edges) edge.classList.toggle('selected', link.source === selected || link.target === selected);
      detail.replaceChildren();
      const type = types.find(item => item.type === name);
      detail.append(element('h2', name + ' · Relations'));
      const relations = Object.entries(type.relations || {});
      if (!relations.length) detail.append(element('p', 'This type has no relations. It can be used as a subject in other types.', 'muted small'));
      for (const [relation, rule] of relations) {
        const card = element('article', undefined, 'model-relation');
        card.append(element('h3', relation));
        const allowed = type.metadata?.relations?.[relation]?.directly_related_user_types || [];
        card.append(element('pre', expression(rule, allowed), 'model-expression'));
        if (allowed.length) {
          const refs = element('div', undefined, 'model-references'); refs.append(element('span', 'Accepts', 'small muted'));
          for (const ref of allowed) {
            const button = element('button', restriction(ref), 'quiet'); button.type = 'button';
            if (positions.has(ref.type)) button.addEventListener('click', () => choose(ref.type));
            else button.disabled = true;
            refs.append(button);
          }
          card.append(refs);
        }
        detail.append(card);
      }
    }
    selector.addEventListener('change', () => choose(selector.value)); choose(selected);
    if (Object.keys(model.conditions || {}).length) {
      const conditions = element('details'); conditions.append(element('summary', 'Model conditions'));
      for (const [name, condition] of Object.entries(model.conditions)) {
        conditions.append(element('h3', name), element('pre', condition.expression, 'model-expression'), element('pre', JSON.stringify(condition.parameters || {}, null, 2), 'code-panel'));
      }
      container.append(conditions);
    }
  }
  const api = {expression, links, render};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KengenModel = api;
})(globalThis);
