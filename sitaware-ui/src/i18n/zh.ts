export default {
  app: { title: '态势感知', subtitle: 'SitAware' },
  nav: {
    dashboard: '仪表盘', events: '事件', alerts: '告警', query: '查询', route: '路径', export: '导出',
  },
  city: { label: '城市', guangzhou: '广州', shenzhen: '深圳', beijing: '北京', shanghai: '上海', chengdu: '成都' },
  metrics: { total: '事件总数', today: '今日', highRisk: '高危', riskLevel: '风险等级' },
  filters: {
    type: '类型', severity: '严重度', source: '来源', search: '搜索', reset: '重置',
    all: '全部',
  },
  severity: { low: '低', medium: '中', high: '高', critical: '危急' },
  type: {
    protest: '集会', accident: '事故', weather: '气象', signal: '信号', hazard: '灾害', custom: '其他',
  },
  source: {
    news: '新闻', rss: 'RSS', ham_radio: '火腿', sensor: '传感器', user: '用户', weather: '气象',
  },
  layers: { events: '事件', heat: '热力', ham: '电台', weather: '气象' },
  event: { detail: '事件详情', verify: '标记已验证', untrust: '不可信', rawRefs: '原始链接', flyTo: '定位' },
  time: { axis: '时间轴', play: '播放', pause: '暂停', density: '事件密度', all: '全部时段' },
  alert: {
    title: '告警规则', name: '名称', area: '区域', minSev: '最低严重度', types: '事件类型',
    create: '新建', delete: '删除', notify: '声音', enabled: '启用', none: '暂无规则',
  },
  query: {
    placeholder: '例如：广州天河区现在安全吗？', ask: '询问', history: '历史', local: '本地处理',
    cited: '引用事件', mapAction: '地图动作',
  },
  route: {
    title: '路径规划', start: '起点', end: '终点', avoid: '避风险', plan: '规划', primary: '主路线',
    alt: '替代路线', risk: '风险段落', distance: '距离', duration: '时长', source: '来源',
    fallback: '直线降级（未接入路网）',
  },
  export: {
    title: '导出与分享', geojson: 'GeoJSON', csv: 'CSV', markdown: 'Markdown 报告', snapshot: '地图快照',
    share: '分享链接', copy: '复制', copied: '已复制',
  },
  status: { online: '已连接', offline: '已断开', events: '事件', subscribers: '订阅者' },
  common: { close: '关闭', loading: '加载中…', empty: '暂无数据' },
  sse: { live: '实时' },
}
