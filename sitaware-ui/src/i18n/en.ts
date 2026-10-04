export default {
  app: { title: 'Situation', subtitle: 'SitAware' },
  nav: {
    dashboard: 'Dashboard', events: 'Events', alerts: 'Alerts', query: 'Query', route: 'Route', export: 'Export',
  },
  city: { label: 'City', guangzhou: 'Guangzhou', shenzhen: 'Shenzhen', beijing: 'Beijing', shanghai: 'Shanghai', chengdu: 'Chengdu' },
  metrics: { total: 'Total', today: 'Today', highRisk: 'High-risk', riskLevel: 'Risk' },
  filters: {
    type: 'Type', severity: 'Severity', source: 'Source', search: 'Search', reset: 'Reset', all: 'All',
  },
  severity: { low: 'Low', medium: 'Medium', high: 'High', critical: 'Critical' },
  type: {
    protest: 'Protest', accident: 'Accident', weather: 'Weather', signal: 'Signal', hazard: 'Hazard', custom: 'Other',
  },
  source: {
    news: 'News', rss: 'RSS', ham_radio: 'Ham', sensor: 'Sensor', user: 'User', weather: 'Weather',
  },
  layers: { events: 'Events', heat: 'Heat', ham: 'Stations', weather: 'Weather' },
  event: { detail: 'Event detail', verify: 'Mark verified', untrust: 'Untrust', rawRefs: 'Raw refs', flyTo: 'Locate' },
  time: { axis: 'Timeline', play: 'Play', pause: 'Pause', density: 'Density', all: 'All time' },
  alert: {
    title: 'Alert rules', name: 'Name', area: 'Area', minSev: 'Min severity', types: 'Types',
    create: 'Create', delete: 'Delete', notify: 'Sound', enabled: 'Enabled', none: 'No rules',
  },
  query: {
    placeholder: 'e.g. Is Tianhe, Guangzhou safe now?', ask: 'Ask', history: 'History', local: 'Local',
    cited: 'Cited events', mapAction: 'Map action',
  },
  route: {
    title: 'Route', start: 'Start', end: 'End', avoid: 'Avoid risk', plan: 'Plan', primary: 'Primary',
    alt: 'Alternative', risk: 'Risk segment', distance: 'Distance', duration: 'Duration', source: 'Source',
    fallback: 'Straight-line fallback (no road network)',
  },
  export: {
    title: 'Export & Share', geojson: 'GeoJSON', csv: 'CSV', markdown: 'Markdown', snapshot: 'Snapshot',
    share: 'Share link', copy: 'Copy', copied: 'Copied',
  },
  status: { online: 'Online', offline: 'Offline', events: 'events', subscribers: 'subscribers' },
  common: { close: 'Close', loading: 'Loading…', empty: 'No data' },
  sse: { live: 'Live' },
}
