"""Engineering diagrams inspired by the supplied course's native architecture figures.
Edit CONFIG and the five drawing functions, then run directly from an IDE.
Exports matching SVG and editable diagrams.net XML; no network or model call.
"""
from pathlib import Path
from html import escape
from xml.etree import ElementTree as ET
import json
from copy import deepcopy

CONFIG = {
    "root": Path(__file__).resolve().parents[1],
    "output": "docs/assets/architecture/structured",
    "font": "Arial, PingFang SC, Microsoft YaHei, sans-serif",
    "text": "#151515",
    "fill": "#e2edff",
    "border": "#8ca4ff",
    "edge": "#315bff",
    "boundary": "#2196ff",
    "header": "#315bff",
    "english_readme_diagrams": True,
    "node_font_size": 18,
    "line_height": 26,
}
OUT = CONFIG["root"] / CONFIG["output"]
OUT.mkdir(parents=True, exist_ok=True)
MANIFEST = []


class Diagram:
    def __init__(self, name, title, width, height):
        self.name, self.title, self.width, self.height = name, title, width, height
        self.frames, self.nodes, self.edges, self.labels = [], [], [], []

    def frame(self, key, x, y, w, h, title, size=20):
        self.frames.append(dict(id=key, x=x, y=y, w=w, h=h, title=title, size=size))
        return key

    def node(self, key, x, y, w, h, lines, shape="rect", size=None, fill=None, color=None):
        if isinstance(lines, str):
            lines = lines.split("\n")
        self.nodes.append(dict(id=key, x=x, y=y, w=w, h=h, lines=lines,
                               shape=shape, size=size or CONFIG["node_font_size"],
                               fill=fill or CONFIG["fill"], color=color or CONFIG["text"]))
        return key

    def edge(self, source, target, points, label=None, at=None, dash=False):
        assert len(points) >= 2
        for a, b in zip(points, points[1:]):
            assert a[0] == b[0] or a[1] == b[1], (self.name, points)
        self.edges.append(dict(source=source, target=target, points=points, dash=dash))
        if label:
            assert at is not None
            self.labels.append(dict(x=at[0], y=at[1], value=label))

    def svg_text(self, x, y, value, size=18, color=None, weight=400, anchor="middle"):
        return (f'<text x="{x}" y="{y}" font-size="{size}" '
                f'fill="{color or CONFIG["text"]}" font-weight="{weight}" '
                f'text-anchor="{anchor}">{escape(value)}</text>')

    def save_svg(self):
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
                 f'height="{self.height}" viewBox="0 0 {self.width} {self.height}" '
                 f'role="img" aria-label="{escape(self.title)}">',
                 f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
                 f'markerWidth="8" markerHeight="8" orient="auto"><path d="M0 0L10 5L0 10Z" '
                 f'fill="{CONFIG["edge"]}"/></marker></defs>',
                 f'<rect width="{self.width}" height="{self.height}" fill="white"/>',
                 f'<g font-family="{CONFIG["font"]}">',
                 self.svg_text(30, 35, self.title, 24, anchor="start")]
        for f in self.frames:
            parts.append(f'<rect x="{f["x"]}" y="{f["y"]}" width="{f["w"]}" '
                         f'height="{f["h"]}" rx="8" fill="none" '
                         f'stroke="{CONFIG["boundary"]}" stroke-width="1.2" stroke-dasharray="6 5"/>')
            parts.append(self.svg_text(f["x"]+f["w"]/2, f["y"]+31, f["title"], f["size"]))
        for edge in self.edges:
            d = "M" + " L".join(f"{x},{y}" for x, y in edge["points"])
            dash = ' stroke-dasharray="6 5"' if edge["dash"] else ""
            parts.append(f'<path d="{d}" fill="none" stroke="{CONFIG["edge"]}" '
                         f'stroke-width="1.4" marker-end="url(#arrow)"{dash}/>')
        for n in self.nodes:
            x, y, w, h = (n[k] for k in ("x", "y", "w", "h"))
            parts.append(f'<g data-box="{x},{y},{w},{h}" data-node="{n["id"]}">')
            attrs = f'fill="{n["fill"]}" stroke="{CONFIG["border"]}" stroke-width="1.2"'
            if n["shape"] == "diamond":
                parts.append(f'<path d="M{x+w/2},{y} L{x+w},{y+h/2} L{x+w/2},{y+h} L{x},{y+h/2} Z" {attrs}/>')
            elif n["shape"] == "cylinder":
                r = 11
                parts.append(f'<path d="M{x},{y+r} C{x},{y-r/3} {x+w},{y-r/3} {x+w},{y+r} '
                             f'L{x+w},{y+h-r} C{x+w},{y+h+r/3} {x},{y+h+r/3} {x},{y+h-r} Z" {attrs}/>')
                parts.append(f'<path d="M{x},{y+r} C{x},{y+2.3*r} {x+w},{y+2.3*r} {x+w},{y+r}" '
                             f'fill="none" stroke="{CONFIG["border"]}" stroke-width="1.2"/>')
            else:
                rx = h/2 if n["shape"] == "terminal" else 2
                parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" {attrs}/>')
            line_height = CONFIG["line_height"]
            start = y + h/2 - (len(n["lines"])-1)*line_height/2 + n["size"]*.35
            if n["shape"] == "cylinder":
                start += 7
            for i, value in enumerate(n["lines"]):
                parts.append(self.svg_text(x+w/2, start+i*line_height, value, n["size"], n["color"]))
            parts.append('</g>')
        for label in self.labels:
            value, x, y = label["value"], label["x"], label["y"]
            w = sum(8 if ord(c)<128 else 16 for c in value) + 12
            parts.append(f'<rect x="{x-w/2}" y="{y-17}" width="{w}" height="23" fill="white"/>')
            parts.append(self.svg_text(x, y, value, 16, CONFIG["edge"]))
        parts.append('</g></svg>')
        (OUT / f'{self.name}.svg').write_text(''.join(parts))

    def save_drawio(self):
        document = ET.Element('mxfile', host='app.diagrams.net', version='24.7.17')
        diagram = ET.SubElement(document, 'diagram', id=self.name, name=self.title)
        model = ET.SubElement(diagram, 'mxGraphModel', dx=str(self.width), dy=str(self.height),
                              grid='1', gridSize='10', guides='1', tooltips='1', connect='1',
                              arrows='1', fold='1', page='1', pageScale='1',
                              pageWidth=str(self.width), pageHeight=str(self.height), math='0', shadow='0')
        root = ET.SubElement(model, 'root')
        ET.SubElement(root, 'mxCell', id='0')
        ET.SubElement(root, 'mxCell', id='1', parent='0')
        common = f'html=0;fontFamily=Arial;fontColor={CONFIG["text"]};strokeWidth=1.2;'
        def cell(key, value, x, y, w, h, style):
            el = ET.SubElement(root, 'mxCell', id=key, value=value, style=style,
                               vertex='1', parent='1')
            ET.SubElement(el, 'mxGeometry', x=str(x), y=str(y), width=str(w),
                          height=str(h), **{'as':'geometry'})
            return el
        cell('title', self.title, 30, 10, self.width-60, 40,
             common+'text;align=left;verticalAlign=middle;fontSize=24;')
        by_id = {}
        for f in self.frames:
            by_id[f['id']] = f
            cell(f['id'], f['title'], f['x'], f['y'], f['w'], f['h'],
                 common+f'rounded=1;arcSize=3;dashed=1;dashPattern=6 5;fillColor=none;'
                 f'strokeColor={CONFIG["boundary"]};fontSize={f["size"]};'
                 'verticalAlign=top;spacingTop=10;container=0;')
        for n in self.nodes:
            by_id[n['id']] = n
            shape = {'rect':'rounded=0;', 'terminal':'rounded=1;arcSize=50;',
                     'diamond':'rhombus;', 'cylinder':'shape=cylinder;size=11;'}[n['shape']]
            cell(n['id'], '\n'.join(n['lines']), n['x'], n['y'], n['w'], n['h'],
                 common+shape+f'fontSize={n["size"]};fillColor={n["fill"]};'
                 f'strokeColor={CONFIG["border"]};fontColor={n["color"]};align=center;verticalAlign=middle;')
        for i, edge in enumerate(self.edges):
            source, target = by_id[edge['source']], by_id[edge['target']]
            a, b = edge['points'][0], edge['points'][-1]
            sx, sy = (a[0]-source['x'])/source['w'], (a[1]-source['y'])/source['h']
            tx, ty = (b[0]-target['x'])/target['w'], (b[1]-target['y'])/target['h']
            assert 0 <= sx <= 1 and 0 <= sy <= 1 and 0 <= tx <= 1 and 0 <= ty <= 1, edge
            style = (f'edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;strokeColor={CONFIG["edge"]};'
                     f'strokeWidth=1.4;endArrow=block;endFill=1;exitX={sx};exitY={sy};'
                     f'entryX={tx};entryY={ty};exitPerimeter=0;entryPerimeter=0;')
            if edge['dash']:
                style += 'dashed=1;dashPattern=6 5;'
            el = ET.SubElement(root, 'mxCell', id=f'edge{i}', edge='1', parent='1',
                               source=edge['source'], target=edge['target'], style=style)
            geo = ET.SubElement(el, 'mxGeometry', relative='1', **{'as':'geometry'})
            arr = ET.SubElement(geo, 'Array', **{'as':'points'})
            for x,y in edge['points'][1:-1]:
                ET.SubElement(arr, 'mxPoint', x=str(x), y=str(y))
        for i, label in enumerate(self.labels):
            w = sum(8 if ord(c)<128 else 16 for c in label['value']) + 12
            cell(f'label{i}', label['value'], label['x']-w/2, label['y']-19, w, 27,
                 common+f'text;align=center;verticalAlign=middle;fontSize=16;'
                 f'fontColor={CONFIG["edge"]};fillColor=#ffffff;')
        ET.indent(document)
        ET.ElementTree(document).write(OUT/f'{self.name}.drawio', encoding='utf-8', xml_declaration=True)

    def save(self, english=None):
        self.save_drawio()
        self.save_svg()
        MANIFEST.append(dict(name=self.name, width=self.width, height=self.height,
                             nodes=len(self.nodes), edges=len(self.edges)))
        if english and CONFIG["english_readme_diagrams"]:
            translated = deepcopy(self)
            translated.name += '.en'
            translated.title = english['title']
            for frame in translated.frames:
                frame['title'] = english['frames'][frame['id']]
            for node in translated.nodes:
                node['lines'] = english['nodes'][node['id']]
            for label in translated.labels:
                label['value'] = english['labels'][label['value']]
            translated.save()


OVERALL_EN = {
    'title': 'Tripal System Architecture',
    'frames': {'client':'User access', 'app':'Application services', 'execution':'Planning runtime',
               'capabilities':'Models / Tools / Documents', 'data':'Data storage'},
    'nodes': {
        'web':['Web workspace','React'], 'mcp_client':['MCP client','Optional access'],
        'api':['FastAPI','REST / SSE'],
        'business':['Travel services','Requirements / Trip revisions','Daily plans / Documents / Exports'],
        'mcp':['MCP stdio server','JSON-RPC / Scope / Audit'],
        'dispatch':['Task registration / Dispatch','SQL queued → Dispatcher'],
        'worker':['Celery Worker','Task leases / Heartbeats'],
        'graph':['LangGraph','Research / Arrange','Validate / Review'],
        'harness':['Execution harness','Budgets / Scopes / Checks'],
        'model':['Model gateway','Switchable model providers'],
        'tools':['Travel fact tools','AMap / Meituan'],
        'rag':['Private-document RAG','Parse / Search / Sources'],
        'sql':['MySQL','Trips / Checkpoints / Events'],
        'redis':['Redis','Task messages / Cache'],
        'es':['Elasticsearch','Text / Vector search indexes'],
        'files':['Local files','Documents / Attachments'],
    },
    'labels': {'HTTP / SSE':'HTTP / SSE', '生成 / 调整':'Plan / Revise',
               'Redis / Celery':'Redis / Celery', 'stdio':'stdio',
               'Provider / RAG 调用':'Provider / RAG calls',
               '任务 / 检查点 / 事件':'Tasks / Checkpoints / Events'},
}

WORKFLOW_EN = {
    'title':'Tripal LangGraph Workflow',
    'frames': {'flow':'Planning workflow', 'recovery':'Interrupt and resume'},
    'nodes': {
        'start':['START'], 'end':['END'], 'pure_end':['END'],
        'requirements':['Confirm requirements','requirements'],
        'delegate':['Select research domains','delegate'],
        'destination':['Research destinations','destination'],
        'research':['Sequential research','research'],
        'arrange':['Arrange daily plans','arrange'],
        'validate':['Validate routes / Constraints','validate'],
        'review':['Review conflicts','review'],
        'variants':['Generate candidates as needed','variants'],
        'narrate':['Explain results','narrate'],
        'strategy':['Pure strategy','conditions met?'],
        'change':['Requirements','changed?'],
        'pure':['Pure-model draft','No tool-based verification'],
        'interrupt':['Missing essential inputs','or first relevant conflict','interrupt()'],
        'checkpoint':['MySQL checkpoint','Persist graph state'],
        'wait':['Wait for the user','Add details / Resolve conflicts'],
        'resume':['Same task thread_id','Command(resume=...)'],
        'return':['Resume the original node','Continue execution'],
    },
    'labels': {'否':'No', '是':'Yes', '是：重新编排':'Yes: rearrange'},
}


def overall():
    d = Diagram('01-overall', 'Tripal 整体架构', 1520, 1000)
    d.frame('client',30,70,230,690,'用户接入')
    d.frame('app',310,70,400,690,'应用服务')
    d.frame('execution',760,70,350,690,'规划执行')
    d.frame('capabilities',1160,70,330,690,'模型、工具与资料')
    d.frame('data',310,810,1180,150,'数据存储')
    d.node('web',50,150,190,84,['Web 工作台','React'])
    d.node('mcp_client',50,550,190,84,['MCP 客户端','可选接入'])
    d.node('api',340,150,340,84,['FastAPI','REST / SSE'])
    d.node('business',340,300,340,116,['旅行业务服务','需求访谈 / 行程版本 / 吃住行','收藏 / 资料 / 分享与导出'])
    d.node('mcp',340,550,340,84,['MCP stdio 服务','JSON-RPC / scope / 审计'])
    d.node('dispatch',790,150,290,84,['任务登记与派发','SQL queued → Dispatcher'])
    d.node('worker',790,300,290,84,['Celery Worker','任务租约 / 心跳 / 执行'])
    d.node('graph',790,470,290,100,['LangGraph','调查 → 编排 → 校验 → 审阅'])
    d.node('harness',790,625,290,76,['Harness','调用预算 / 工具授权 / 执行检查'])
    d.node('model',1190,150,270,84,['模型网关','可切换模型提供者'])
    d.node('tools',1190,320,270,84,['旅行事实工具','高德 / 美团'])
    d.node('rag',1190,490,270,84,['私人资料 RAG','解析 / 混合检索 / 来源'])
    for key,x,title,desc in [('sql',340,'MySQL','业务表 / 检查点 / 事件'),('redis',630,'Redis','任务消息 / 临时缓存'),('es',920,'Elasticsearch','全文 / 向量派生索引'),('files',1210,'本地文件','原文 / 附件 / 路书')]:
        d.node(key,x,865,250,82,[title,desc],shape='cylinder' if key!='files' else 'rect',size=17)
    d.edge('web','api',[(240,192),(340,192)],'HTTP / SSE',(290,180))
    d.edge('api','business',[(510,234),(510,300)])
    d.edge('business','dispatch',[(680,358),(735,358),(735,192),(790,192)],'生成 / 调整',(735,266))
    d.edge('dispatch','worker',[(935,234),(935,300)],'Redis / Celery',(935,275))
    d.edge('worker','graph',[(935,384),(935,470)])
    d.edge('harness','graph',[(935,625),(935,570)],dash=True)
    d.edge('mcp_client','mcp',[(240,592),(340,592)],'stdio',(290,580))
    for key,y in [('model',192),('tools',362),('rag',532)]:
        d.edge('graph',key,[(1080,520),(1135,520),(1135,y),(1190,y)])
    d.edge('mcp','capabilities',[(680,592),(735,592),(735,730),(1160,730)],'Provider / RAG 调用',(950,718))
    d.edge('execution','data',[(935,760),(935,810)],'任务 / 检查点 / 事件',(1080,791))
    d.save(english=OVERALL_EN)


def layered():
    d = Diagram('02-layered', 'Tripal 分层架构', 1440, 940)
    d.frame('system',30,70,1380,830,'旅行规划智能体系统')
    rows = [
        ('交互层',[['React / TypeScript','需求对话 / 地点探索'],['AMap JS SDK','地图 / 路线展示'],['行程工作台','每日安排 / 路书']]),
        ('接入与业务层',[['FastAPI / REST / SSE','认证 / 会话 / 成员权限'],['旅行业务服务','需求访谈 / 行程版本 / 吃住行'],['MCP stdio','工具接口 / scope / 审计']]),
        ('执行与编排层',[['任务派发 / Celery','queued 扫描 / 租约 / 心跳'],['LangGraph / LangChain','领域调查 / 编排 / 约束校验'],['状态恢复 / 候选方案','interrupt / resume / A/B']]),
        ('能力适配层',[['模型网关','结构化输出 / 模型适配'],['高德 / 美团 Provider','地点 / 路线 / 天气 / 商品查询'],['文档 RAG','解析 / BGE / BM25 + kNN']]),
        ('数据与文件层',[['MySQL / Redis','业务事实 / 检查点 / 消息 / 缓存'],['Elasticsearch','512 维向量 / 全文派生索引'],['本地文件 / Mailpit','原文附件 / 测试邮件']]),
        ('执行保障',[['工具授权 / 调用预算','Harness 能力边界'],['权限 / 租约 / 基准版本','结果提交前复查'],['事件 / 业务审计','任务状态与修改记录']]),
    ]
    for i,(title,modules) in enumerate(rows):
        y=130+i*124
        d.node(f'layer{i}',50,y,170,100,title,fill=CONFIG['header'],color='#ffffff',size=20)
        d.frame(f'row{i}',240,y,1150,100,'')
        for j,lines in enumerate(modules):
            d.node(f'l{i}m{j}',260+j*376,y+16,350,68,lines,size=17)
    d.save()


def workflow():
    d = Diagram('03-langgraph','Tripal LangGraph 工作流',1560,1550)
    d.frame('flow',30,70,1100,1440,'规划工作流')
    d.frame('recovery',1180,70,350,1440,'中断与恢复')
    d.node('start',460,130,120,44,'START',shape='terminal')
    steps=[('requirements',205,['需求确认','requirements']),('delegate',455,['领域选择','delegate']),
           ('destination',555,['目的地调查','destination']),('research',655,['按需顺序调查','research']),
           ('arrange',755,['按日编排行程','arrange']),('validate',855,['路线与约束校验','validate']),
           ('review',955,['冲突审阅','review']),('variants',1210,['按需生成候选 A/B','variants']),
           ('narrate',1310,['结果说明','narrate'])]
    for key,y,lines in steps:
        d.node(key,370,y,300,64,lines)
    d.node('strategy',380,310,280,104,['pure 分支','条件成立？'],shape='diamond')
    d.node('change',380,1060,280,104,['需求发生','变化？'],shape='diamond')
    d.node('pure',790,330,270,64,['纯模型草案','pure / 无工具核验'])
    d.node('pure_end',865,455,120,44,'END',shape='terminal')
    d.node('end',460,1410,120,44,'END',shape='terminal')
    d.edge('start','requirements',[(520,174),(520,205)])
    d.edge('requirements','strategy',[(520,269),(520,310)])
    d.edge('strategy','delegate',[(520,414),(520,455)],'否',(542,439))
    d.edge('strategy','pure',[(660,362),(790,362)],'是',(725,350))
    d.edge('pure','pure_end',[(925,394),(925,455)])
    for a,b,ya,yb in [('delegate','destination',519,555),('destination','research',619,655),
                      ('research','arrange',719,755),('arrange','validate',819,855),
                      ('validate','review',919,955),('review','change',1019,1060),
                      ('variants','narrate',1274,1310),('narrate','end',1374,1410)]:
        d.edge(a,b,[(520,ya),(520,yb)])
    d.edge('change','arrange',[(380,1112),(240,1112),(240,787),(370,787)],'是：重新编排',(240,950))
    d.edge('change','variants',[(520,1164),(520,1210)],'否',(542,1192))
    # This is a mechanism sub-diagram; no crossing connectors to the planning spine.
    d.node('interrupt',1215,205,280,116,['必要信息缺失','或首次发现相关冲突','interrupt()'])
    d.node('checkpoint',1215,440,280,100,['MySQL checkpoint','保存图状态'],shape='cylinder')
    d.node('wait',1215,680,280,84,['等待用户','补充信息 / 冲突取舍'])
    d.node('resume',1215,920,280,84,['同一任务 thread_id','Command(resume=...)'])
    d.node('return',1215,1160,280,84,['恢复原中断节点','继续工作流'])
    for a,b,ya,yb in [('interrupt','checkpoint',321,440),('checkpoint','wait',540,680),
                      ('wait','resume',764,920),('resume','return',1004,1160)]:
        d.edge(a,b,[(1355,ya),(1355,yb)])
    d.save(english=WORKFLOW_EN)


def business():
    d = Diagram('04-business','Tripal 业务架构',1520,1030)
    d.frame('planning',30,70,1460,270,'行程规划业务')
    phases=[('need','需求确认\n城市 / 日期 / 预算 / 偏好'),('recommend','调查与推荐\n候选地点 / 草案 / 缺口'),
            ('confirm','方案确认\n比较候选 / 保存版本'),('manage','管理与调整\n按天安排 / 锁定地点'),
            ('export','路书交付\n分享 / PDF / Markdown')]
    for i,(key,label) in enumerate(phases):
        x=60+i*290
        d.node(key,x,155,240,84,label,size=17)
        if i:
            d.edge(phases[i-1][0],key,[(x-50,197),(x,197)])
    d.edge('manage','need',[(1050,239),(1050,298),(180,298),(180,239)],'调整需求，重新规划',(615,287))
    columns=[('discovery',30,'地点与资料',[['地点探索','景点 / 美食 / 住宿'],['地点收藏','保存想去的地点'],['私人资料检索','攻略原文 / 文件名 / 位置']]),
             ('daily',530,'每日行程服务',[['每日安排','地点顺序 / 路线 / 交通方式'],['吃住行与预算','餐厅 / 住宿 / 已知费用'],['修改与版本','锁定地点 / 历史版本']]),
             ('access',1030,'账户与协作',[['账户与会话','身份认证 / 个人资料'],['行程协作','owner / editor / viewer'],['分享与导出','访问控制 / 路书文件']])]
    for key,x,title,nodes in columns:
        d.frame(key,x,400,460,420,title)
        for i,lines in enumerate(nodes):
            d.node(f'{key}{i}',x+50,470+i*110,360,74,lines)
    d.frame('rules',30,870,1460,120,'业务约束')
    for i,text in enumerate(['来源可查看 / 未知信息待核实','修改保留版本 / 按成员权限访问','预订仅记录意向 / 不执行付款']):
        d.node(f'rule{i}',60+i*480,923,440,44,text,size=17)
    d.save()


def technical():
    d = Diagram('05-technical','Tripal 技术架构',1710,1020)
    for key,x,w,title in [('client',30,240,'客户端'),('backend',310,300,'后端服务'),
                           ('execution',650,320,'任务与工作流'),('adapter',1010,300,'能力适配'),
                           ('external',1350,330,'外部平台')]:
        d.frame(key,x,70,w,700,title)
    d.frame('data',310,830,1370,150,'基础服务与文件')
    d.node('web',50,160,200,84,['React / TypeScript','Vite / TanStack Query'],size=16)
    d.node('map',50,340,200,84,['AMap JS SDK','浏览器直连高德底图'],size=16)
    d.node('mcp_client',50,520,200,84,['MCP 客户端','可选 stdio 接入'],size=17)
    d.node('api',330,160,260,84,['FastAPI + Uvicorn','REST / SSE'])
    d.node('business',330,310,260,134,['业务服务','认证 / 成员权限','需求访谈 / 行程版本','吃住行 / 资料 / 导出'])
    d.node('mcp',330,520,260,100,['自实现 MCP stdio','JSON-RPC / scope / 审计','Provider / RAG / 行程工具'],size=17)
    d.node('dispatch',670,160,280,84,['任务派发器','SQL queued 扫描'])
    d.node('worker',670,310,280,84,['Celery Worker','租约 / 心跳 / 版本复查'])
    d.node('graph',670,460,280,84,['LangGraph / LangChain','编排 / 校验 / 中断恢复'])
    d.node('harness',670,620,280,64,['Harness','预算 / 能力授权 / 事件'])
    d.node('model_gateway',1030,160,260,84,['模型网关','模型适配 / 结构化输出'])
    d.node('provider',1030,310,260,84,['Provider 适配器','高德 / 美团 CLI'])
    d.node('rag',1030,460,260,100,['文档 RAG','解析 / BGE 512 维','BM25 + kNN / RRF'])
    d.node('models',1370,160,290,84,['模型 API','OpenAI 兼容 / Gemini / Ollama'],size=16)
    d.node('amap',1370,310,290,84,['高德地图服务','地点 / 路线 / 天气 / 底图'])
    d.node('meituan',1370,460,290,84,['美团官方 CLI','酒旅 / 美食查询'])
    for key,x,lines,shape in [('mysql',330,['MySQL 8.4','SQLAlchemy / Alembic'],'cylinder'),
                             ('redis',600,['Redis 7.4','broker / 候选与缓存'],'cylinder'),
                             ('es',870,['Elasticsearch 8.17','全文 / 向量索引'],'cylinder'),
                             ('files',1140,['本地 data 文件','原文 / 附件'],'rect'),
                             ('mail',1410,['Mailpit','本地测试邮件'],'rect')]:
        d.node(key,x,890,230,82,lines,shape=shape,size=16)
    d.edge('web','api',[(250,202),(330,202)],'HTTP / SSE',(290,190))
    d.edge('api','business',[(460,244),(460,310)])
    d.edge('api','dispatch',[(590,202),(670,202)],'异步任务',(630,190))
    d.edge('dispatch','worker',[(810,244),(810,310)],'Redis / Celery',(810,282))
    d.edge('worker','graph',[(810,394),(810,460)])
    d.edge('harness','graph',[(810,620),(810,544)],dash=True)
    for key,y in [('model_gateway',202),('provider',352),('rag',510)]:
        d.edge('graph',key,[(950,502),(990,502),(990,y),(1030,y)])
    d.edge('model_gateway','models',[(1290,202),(1370,202)])
    d.edge('provider','amap',[(1290,352),(1370,352)])
    d.edge('provider','meituan',[(1290,352),(1330,352),(1330,502),(1370,502)])
    d.edge('mcp_client','mcp',[(250,562),(330,562)],'stdio',(290,550))
    d.edge('mcp','adapter',[(590,570),(630,570),(630,735),(1010,735)],'工具调用',(810,723))
    for source,x,label in [('backend',460,'业务数据'),('execution',810,'消息 / 检查点'),('adapter',1160,'资料索引 / 文件')]:
        d.edge(source,'data',[(x,770),(x,830)],label,(x,807))
    d.save()


if __name__ == '__main__':
    for draw in (overall,layered,workflow,business,technical):
        draw()
    (OUT/'layout-manifest.json').write_text(json.dumps(MANIFEST,ensure_ascii=False,indent=2))
    print(f'Wrote {len(MANIFEST)} SVG + editable drawio diagrams to {OUT}')
