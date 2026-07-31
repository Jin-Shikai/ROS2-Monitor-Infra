# Shikai-Jul17-IK.pdf 教授 Review 完整整理

## 说明

- 来源文件：`Shikai-Jul17-IK.pdf`
- 审阅者标识：`20190404`
- 共识别出 **106 条独立 review**，其中 **104 条便签批注（Sticky Note）**、**2 条高亮文字批注（Comment on Text）**。
- PDF 中另有 106 个 Popup 对象，它们只是便签批注的弹窗外壳；另有 281 个 Link 对象。二者均不是额外 review，因此未重复计入。
- “PDF 页”指 PDF 文件的物理页码。对于便签批注，PDF 并不保存“所选文字”；本文会如实标注“无文本选区”，并给出批注锚点所在的原文句、段、标题或图表，便于定位。

## v3 修改状态总览（2026-07-30 核对）

以 v3 定稿（`Shikai-Jul30-IK_revised_v3.pdf`，由当前 LaTeX 源码编译）逐条核对 106 条 review 的结果：

- **已解决：101 条**
- **部分解决（需小幅补充）：4 条**（39、57、58、70）
- **建议人工复核：1 条**（67）

（2026-07-30 追加：79 已由重绘的 TikZ 数据模型图解决，根元素更名为
DeploymentSpecification；84/96 的四张架构映射图已作为正式插图加入 6.11 节，
图注注明原图出处。）

总体结论：**v3 已实质性回应教授的绝大多数意见**。教授反复强调的四个核心问题——端到端用户工作流（85）、plugin/DSL/converter 故事（50、51、99）、data record 载荷表示（56、57）、现有方法能否被参考架构容纳（84、96）——均已有专门章节和图表落实。剩余项集中在两张 PNG 图（`Components.png`、`CodeGen.png`）的图内文字与正文术语不一致，以及少量可选的补充说明。

### 逐条状态表

| 编号 | 状态 | 核对说明 |
|---|---|---|
| 1 | ✅ | 引言已加入 AI 组件带来的不确定性（感知/决策、置信度、训练分布差异） |
| 2 | ✅ | 已改为 "does not explore every possible execution path" |
| 3 | ✅ | 已改为 "The challenge is to turn ..." |
| 4 | ✅ | 该段内容已移入 Problem Statement，引言以过渡句收尾 |
| 5 | ✅ | 已声明属性规约/检查超出范围，并引用 RV 综述（Leucker、Francalanza） |
| 6 | ✅ | RQ4 使用 "the proposed reference architecture and its implementation" |
| 7 | ✅ | 贡献列表第 5 条明确"减少低层样板代码"；6.9 节给出量化证据 |
| 8 | ✅ | 正向反馈，无需修改 |
| 9 | ✅ | 各图注标明 "Author's illustration based on ..."/"adapted from ..."；四张原论文截图映射 PNG 已弃用，改为自绘对比图与映射表 |
| 10 | ✅ | ComMA 段落已删除，全文不再出现 |
| 11 | ✅ | 核心术语统一为 Property；rule 仅作为一种表示形式出现 |
| 12 | ✅ | 同上，术语表明确 Property 与表示形式的层级 |
| 13 | ✅ | 统一使用 system under monitoring |
| 14 | ✅ | 新增 Property Specification Formalisms 小节（时序逻辑/规则/语法/状态机/流语言） |
| 15 | ✅ | 新增 Alternative Observation Mechanisms（插桩/网络/tracing 三类） |
| 16 | ✅ | 相关信息已整合进 2.3，不再重复出现 |
| 17 | ✅ | 明确 raw observation → common data record → checker-specific event 三层数据形态 |
| 18 | ✅ | 已加"第 4 章将使用该记法"的前向引用 |
| 19 | ✅ | 符号改为文字说明（圆=进程、六边形=trace、方=monitor、外框=location），不再出现未定义字母 |
| 20 | ✅ | DDS/TCP/UDP/HTTP/WebSocket/AMQP/Kafka/MQTT 均有规范或论文引用 |
| 21 | ✅ | MQTT 段说明其用于 split 原型、非架构强制依赖 |
| 22 | ✅ | 第 3 章改为中性综述，比较全部移至第 6 章 |
| 23 | ✅ | ROSMonitoring 首句即 "topic-oriented runtime-verification framework for ROS 1" |
| 24 | ✅ | changes → converts |
| 25 | ✅ | ROSMonitoring 2.0 段落已重写为事实—局限结构 |
| 26 | ✅ | 统一六个 review 问题 + 汇总比较表 |
| 27 | ✅ | FRET 全称展开并定义用途 |
| 28 | ✅ | Copilot/Ogma 已解释；明确非 AI 编程助手 |
| 29 | ✅ | LTTng 全称 + tracepoints 定义 |
| 30 | ✅ | Table 3.1 定义三个观察层级及可见信息 |
| 31 | ✅ | TeSSLa 全称展开（Temporal Stream-based Specification Language） |
| 32 | ✅ | 缩写审计完成（eBPF/XDP/STL 等首次出现均展开），各小节结构统一 |
| 33 | ✅ | 比较表重做：observation / property & checking / execution & placement / configuration & automation |
| 34 | ✅ | 观察元素表使用全称表头（Topics/Services/Actions/Parameters/Lifecycle states/Kernel events） |
| 35 | ✅ | 与本论文的对比移至第 6 章（coverage comparison + accommodation） |
| 36 | ✅ | Research Gaps 节只谈缺口，不谈贡献 |
| 37 | ✅ | gap 以列表呈现，覆盖配置灵活性、自动化、可替换性等维度 |
| 38 | ✅ | 章标题改为 "Towards a Reference Architecture for Configurable ROS 2 Monitoring" |
| 39 | 🔶 | 已改横向整页（sidewaysfigure）且域模型与原型配置拆为两图；**最终 PDF 100% 缩放下的最小字号仍需人工确认** |
| 40 | ✅ | 已补模型动机与获取方法（文献抽取、合并同义、建立跨树约束） |
| 41 | ✅ | 明确 oracle 在 passive/active 两种模式下均适用 |
| 42 | ✅ | passive/active 改为 or-group，可共存 |
| 43 | ✅ | application-level 已定义（ROS 2 图暴露的类型化数据），并有层级表支撑 |
| 44 | ✅ | 新增 "How the Model Is Used" + 配置工作流图 + Prototype 范围说明 |
| 45 | ✅ | parameters 明确列为未选择/未实现的变体 |
| 46 | ✅ | 明确 feature 选择之外还需 hosts/links/transport 等部署信息 |
| 47 | ✅ | common data record 首次出现即定义，细节前向引用 4.5 与附录 |
| 48 | ✅ | R4（自定义转换与属性形式）与 R7（可扩展性）已写为需求 |
| 49 | ✅ | 参考架构按图中编号逐步解释 |
| 50 | ✅ | DSL 已定义；converter 必要性（每个 checker 需要自己的输入格式）已说明 |
| 51 | ✅ | plugin 定义、接口、加载方式在设计章 + 实现章 + 附录契约三处覆盖 |
| 52 | ✅ | feedback 在架构图（虚线）、正文、限制三处一致标注"架构考虑、原型未实现" |
| 53 | ✅ | 改为架构与实现共用同一组角色名 |
| 54 | ✅ | 参考架构图已用 TikZ 重绘，Collectors/Transformers/Dispatcher/Converter/Verdict service 与正文一一对应 |
| 55 | ✅ | schema 与完整示例移入附录，仓库 URL 在附录给出 |
| 56 | ✅ | 附录给出带类型的字段 schema 表 |
| 57 | 🔶 | 已说明 primitive/嵌套消息/数组/时间的递归 JSON 转换规则；**NaN/Inf、byte 数据、bounded types 等边界情况未明说**，如需可补一句 |
| 58 | 🔶 | 附录给出完整 topic record 示例；**service/action 记录示例未并列展示**（正文有字段说明，可选补充） |
| 59 | ✅ | 指代已消除，integrated/split 首次出现即各有定义 |
| 60 | ✅ | 第 2 章部署术语即定义 integrated/split 并映射到监控组织形式 |
| 61 | ✅ | ROS 2-facing 在设计章定义；引言首次出现加了内联注释 |
| 62 | ✅ | host/runtime/process 术语明确（runtime = 一个 YAML 构建的可执行进程） |
| 63 | ✅ | 部署视图改为自定义记法并在正文声明（外框=host、内框=runtime），不再声称严格 UML |
| 64 | ✅ | 明确两种部署是"代表性端点，非完整目录"，架构允许更多放置 |
| 65 | ✅ | 所有图均正文先引用后解释 |
| 66 | ✅ | split 部署图有对应解释段落 |
| 67 | ⏳ | 相关图已全部用 TikZ 重绘、箭头语义在图注说明；**建议终稿前把所有图的箭头/符号再过一遍**（源码层面无法确认视觉效果） |
| 68 | ✅ | Observation Sequence 已移到 Deployment Views 之前 |
| 69 | ✅ | 第 4 章新增 Chapter Summary |
| 70 | 🔶 | 已有 Code Organization 小节与目录职责表；**仓库 URL 仅在附录出现**，建议该节顺带给出 |
| 71 | ✅ | 实现章开篇即给 implementation chain 总览图（规约→生成→运行时） |
| 72 | ✅ | runtime pipeline 图先行，正文按图解释 |
| 73 | ✅ | 原 5.7 重写为 Checking Graph 小节：先定义、再 YAML 示例、后构建过程 |
| 74 | ✅ | runtime 在实现章开头与第 2 章术语表均有定义 |
| 75 | ✅ | checking graph 已定义（并明确"不是 ROS graph"） |
| 76 | ✅ | Verifier Runtime 小节重写：是什么、输入哪来、可承载什么角色 |
| 77 | ✅ | 新增 Anatomy of a Monitoring Solution：authored/generated/reused 三栏表 |
| 78 | ✅ | 正文按 Figure（hosts→runtimes→sources→links）层级讲解 |
| 79 | ✅ | 数据模型图已用 TikZ 重绘（`figures/config_generation_model.tex`），根元素更名为 DeploymentSpecification，其余细节与原图一致；正文、算法、图三处术语已统一 |
| 80 | ✅ | 已用精确部署用语（robot-side host 等） |
| 81 | ✅ | projection 弃用，改为 generation procedure |
| 82 | ✅ | 算法标题改为 "Generate runtime YAML configurations from a deployment specification" |
| 83 | ✅ | 弃用 realistic，明确定义 representative 并限定其含义 |
| 84 | ✅ | 6.11 Accommodation：四个方法逐一映射表 + Direct/Adapter/Extension 三级判定，未映射部分如实标注；四张视觉映射图已插入对应小节，图注引用原论文 |
| 85 | ✅ | 6.3 给出五步用户工作流；设计章有对应概念流程图 |
| 86 | ✅ | 明确 E3–E5 用 Gazebo，E1/E2 用确定性刺激进程 |
| 87 | ✅ | Table（specified/generated/property-specific/reused）覆盖全部五个实验 |
| 88 | ✅ | 各实验明确预期/实际验证结果，并说明"无基础设施故障、负面 verdict 为设计刺激" |
| 89 | ✅ | service introspection 机制图（2.3.2）+ collectors 小节说明 services/actions 捕获路径 |
| 90 | ✅ | 已说明重复运行 speed 属性是为验证序列化与 MQTT 传输保真 |
| 91 | ✅ | Pi reference verifier 定义为仅作对照、非生产组件 |
| 92 | ✅ | E5 部署图已重绘，图内文字直接说明 reference verifier 的用途 |
| 93 | ✅ | 资源/延迟结果已表格化（v3 进一步删除了正文对表格数字的重复） |
| 94 | ✅ | 6.9：职责对比表 + 约 4200 行复用框架代码 vs 约 260 行属性代码 |
| 95 | ✅ | C1–C5 评价标准在第 6 章开头定义并溯源到需求与 gap |
| 96 | ✅ | 幻灯片映射分析已转为正式的 accommodation 小节与映射表 |
| 97 | ✅ | Discussion 按 RQ1–RQ4 组织 |
| 98 | ✅ | trade-offs 分类列点（reduction vs evidence、integrated vs split 等五类） |
| 99 | ✅ | plugin 故事完整：定义→接口→注册→四个案例插件→附录契约→Discussion 界定其范围 |
| 100 | ✅ | Threats 按 internal/external 分类 |
| 101 | ✅ | 遗漏相关工作已列为 external validity 威胁，且 gap 表述限定为"reviewed work" |
| 102 | ✅ | Future work 按六个主题列点 |
| 103 | ✅ | Conclusion 每个 RQ 只给简短最终答案，不重复论证 |
| 104 | ✅ | RQ 原文在 Discussion 与 Conclusion 逐字重述 |
| 105 | ✅ | Future work 只保留在 Discussion（"consolidated here"），Conclusion 不再重复 |
| 106 | ✅ | 附录给出 GitHub 仓库链接及内容说明 |

### v3 额外发现并修复的问题（教授未提出）

- Design 章总览图的图注描述的是另一张图的内容（collectors/transformers），与 `Components.png` 实际所示（Monitors/Filters/Exporters + Feedback Runtime）不符——图注与正文已重写，并明确标注图中含原型未实现的架构元素。
- Discussion RQ1 中"没有任何被综述方法将采集与检查分进程且保持可配置"的论断与第 3 章自述矛盾（ROSMonitoring 外部 oracle、Aldegheri 可迁移容器），已收窄为可辩护的表述。
- 全文 -ise/-ize 拼写混用已统一为 Oxford 风格（behaviour + -ize）；另修复若干术语漂移（deployment configuration→specification 等）与一处断行连字符错误。

### 仍建议在提交前处理（详见 `Shikai-Jul30-IK_major_issues_v3.md`）

1. 重绘 `Components.png`，使图内标签与正文角色名一致（54 的余留；`CodeGen.png` 已于 7-30 重绘解决）。
2. E4 与 E5 同一任务的 robot-2 speed 判定次数不同（20 vs 18），建议加一句说明系不同运行的正常波动。
3. 封面日期 "June 2026" 与答辩时间是否一致；`\secondCommitteeMember` 为空。
4. 终稿 100% 缩放检查 feature model 与横排大图的最小字号（39、67）。

---

## 逐条整理

### 1（PDF 页 6）

- **所选原文**：便签批注，无文本选区；锚定于引言段落：“Robots often work in changing environments. Their behaviour depends on software, hardware, sensor data, communication, and the physical world.”
- **Review 原文**：“You can also add that robots use more and more AI components that may introduce uncertainty.”
- **中文意思**：还可以补充说明，机器人越来越多地使用 AI 组件，而这些组件可能引入不确定性。
- **我的修改意见**：在该段列举不确定性来源时加入 AI/ML 组件，例如感知与决策模型的非确定性、分布漂移和置信度变化，并说明这进一步强化了运行时监控的必要性。

### 2（PDF 页 6）

- **所选原文**：便签批注，无文本选区；锚定句：“Unlike model checking, runtime monitoring does not study every possible system state.”
- **Review 原文**：“Instead of state say 'every possible execution path'”
- **中文意思**：不要使用 “state”，改成 “every possible execution path（每一条可能的执行路径）”。
- **我的修改意见**：将原句改为：“Unlike model checking, runtime monitoring does not explore every possible execution path; it analyses the behaviour observed in actual executions.” 这样比较对象更准确。

### 3（PDF 页 6）

- **所选原文**：便签批注，无文本选区；锚定句：“The difficult part is turning these possibilities into a reusable monitoring setup...”
- **Review 原文**：“The challenge is to turn ....”
- **中文意思**：建议用 “The challenge is to turn ...” 来表述该句，使问题陈述更直接。
- **我的修改意见**：把句首改为 “The challenge is to turn these observation mechanisms into a reusable and configurable monitoring infrastructure.”，随后明确列出需要配置的观察源、处理、传输、检查和部署选择。

### 4（PDF 页 6）

- **所选原文**：便签批注，无文本选区；锚定于引言最后一段，该段已开始讨论具体困难与问题。
- **Review 原文**：“In principle, this last paragraph can be moved to the next section. It already provides some hints to the problem”
- **中文意思**：原则上可以把最后一段移到下一节，因为它已经开始提示/讨论研究问题。
- **我的修改意见**：将该段移至 Problem Statement 一节开头；引言只保留背景和动机。移动后用一句过渡语连接：“These observations lead to the problem addressed in the next section.”

### 5（PDF 页 7）

- **所选原文**：“Rule specification and checking”
- **Review 原文**：“You can say that this is an important problem but it is considered out of the scope for this thesis. You can refer to the general literature on runtime verification for the available approaches there”
- **中文意思**：可以说明规则/属性的规约与检查是一个重要问题，但不属于本论文范围；可引用运行时验证领域的一般文献介绍现有方法。
- **我的修改意见**：明确写出 scope boundary：论文关注可配置的观察与监控基础设施，不提出新的属性语言或检查算法；属性规约和检查由外部工具/插件承担。补充 1-2 篇 runtime verification 综述或经典文献作为入口。

### 6（PDF 页 8）

- **所选原文**：“implemented infrastructure”
- **Review 原文**：“May be use 'the proposed reference architecture and its implementation'”
- **中文意思**：可以改用 “the proposed reference architecture and its implementation（所提出的参考架构及其实现）”。
- **我的修改意见**：在 RQ4 或相关表述中用教授建议的短语，避免只评价实现而遗漏架构层贡献；同时确保后续评价分别覆盖 architecture coverage 与 prototype implementation。

### 7（PDF 页 9）

- **所选原文**：便签批注，无文本选区；锚定于贡献总结段：“The main contribution is the reusable monitoring architecture and the infrastructure that realizes it.”
- **Review 原文**：“It also automates the implementation of monitoring solutions by reducing the need to write low level routine boilerplate code”
- **中文意思**：该方法还通过减少低层、重复的样板代码，自动化了监控方案的实现。
- **我的修改意见**：在贡献列表中新增“自动化生成/组装”贡献，并在评价章节用可量化证据支撑，例如生成的配置文件数、框架复用代码量、用户仅需实现的插件代码量，以及与手工实现的对比。

### 8（PDF 页 9）

- **所选原文**：便签批注，无文本选区；锚定于第 1 章结尾。
- **Review 原文**：“I am glad to see that the quality of the text improved compared to the previous version!”
- **中文意思**：教授认为与上一版相比，文本质量已有提升。
- **我的修改意见**：这是正向反馈，不要求实质修改。保持当前行文风格，并在后续重写时维持术语一致、句子简洁和段落逻辑。

### 9（PDF 页 11）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 2.1 “Topic communication” 和 Figure 2.2 “Service communication”。
- **Review 原文**：“If you have taken the pictures from somewhere else, please provide a reference”
- **中文意思**：如果图片取自其他来源，请提供引用。
- **我的修改意见**：逐图确认来源。若改绘自 ROS 2 官方文档，在图注写 “Adapted from ...” 并加入参考文献；若完全自制，可在正文或图注注明 “Author’s own illustration”，同时保留可追溯的源文件。新加入的四张架构映射图直接包含论文原图，因此必须在每张图注中标明原图论文和 Figure 编号，并区分 “source architecture” 与 “author’s mapping”；若不是重新绘制，还需核对出版方的图片复用许可。

### 10（PDF 页 13）

- **所选原文**：便签批注，无文本选区；锚定于介绍 ComMA 的段落：“The same basic roles appear in model-driven runtime-verification approaches such as ComMA...”
- **Review 原文**：“I would drop this paragraph”
- **中文意思**：教授建议删除这一段。
- **我的修改意见**：删除该段；若 ComMA 对 related work 确有必要，则移入第 3 章相应小节，不要在基础概念章节提前展开。

### 11（PDF 页 13）

- **所选原文**：便签批注，无文本选区；锚定于术语定义：“Rule — An expected condition that the observed behaviour is checked against. The literature also calls this a property.”
- **Review 原文**：“Why not just call it property?”
- **中文意思**：为什么不直接称为 “property（属性）”？
- **我的修改意见**：将核心术语从 Rule 统一改为 Property；仅当具体实现使用规则语法时再说明 “a property may be encoded as a rule”。同步修改图、表、RQ、接口说明和全文术语。

### 12（PDF 页 13）

- **所选原文**：便签批注，无文本选区；锚定于监控概念图中的 “Rule”。
- **Review 原文**：“I think property is the more general term. Then a property can be expressed in a rule but it can also be expressed in many other ways. So I suggest to replace Rule with Property”
- **中文意思**：Property 是更一般的术语；属性可以表示为规则，也可以用多种其他方式表示，因此建议用 Property 替换 Rule。
- **我的修改意见**：采纳并在术语表中明确层级：Property 是待检查的行为要求；Specification Formalism 是表示方式；Rule 只是可能的具体编码。将图中 “Rule” 改为 “Property specification”。

### 13（PDF 页 14）

- **所选原文**：便签批注，无文本选区；锚定句：“It does not change the behaviour of the application.”
- **Review 原文**：“application -> system under monitoring”
- **中文意思**：把 “application” 改为 “system under monitoring（被监控系统）”。
- **我的修改意见**：替换该处用词，并全篇统一使用 “system under monitoring (SuM)” 或不缩写的完整术语，避免 application、robot、system 混用造成范围不一致。

### 14（PDF 页 14）

- **所选原文**：便签批注，无文本选区；锚定于 2.2 节末、2.3 节开始之前。
- **Review 原文**：“I would add 2.2.5 that mentions briefly the main ways to specify the properties: temporal logics, rules, grammars, state machines, etc.”
- **中文意思**：建议新增 2.2.5，小结属性规约的主要方式，例如时序逻辑、规则、语法、状态机等。
- **我的修改意见**：增加 “Property Specification Formalisms” 小节，每类用 1-2 句说明表达能力和典型工具，并引用综述/代表性文献；最后说明本论文对具体形式保持中立，通过 converter/verdict-service 接口适配。

### 15（PDF 页 15）

- **所选原文**：便签批注，无文本选区；锚定于 2.3 节对 ROS 2 原生观察机制的描述之后。
- **Review 原文**：“Here I would add the following: what was just described is using the native ROS2 mechanisms for observation. But you need to mention other possibilities as well. For example, using networking sniffing tools like Wireshark, or using instrumentation of the ROS application to include specific monitoring mechanism or even altering the ROS2 itself to provide observability. For each of this there are papers. Alternatively, you can include this discussion in the related work”
- **中文意思**：前文描述的是利用 ROS 2 原生机制进行观察，但还应提到其他方式，例如 Wireshark 等网络嗅探、对 ROS 应用进行插桩、甚至修改 ROS 2 本身以提供可观察性；每种方式都有相关论文，也可放到 related work 中讨论。
- **我的修改意见**：在 2.3 节增加观察机制分类：原生 ROS 2 API、网络层嗅探、应用插桩、ROS 2/中间件插桩、系统级 tracing。每类说明可见数据、侵入性、开销与局限，并在第 3 章映射到相关工作。

### 16（PDF 页 15）

- **所选原文**：便签批注，无文本选区；锚定句：“In ROS 2, this can mean subscribing to topics, reading service events, observing action feedback, sniffing network traffic, using lower-level tracing tools, or even instrumenting the application code.”
- **Review 原文**：“So, if you look at my previous comment, the info I asked for is actually included here”
- **中文意思**：教授指出，上一条意见要求的信息其实已经在此处出现。
- **我的修改意见**：不要重复新增大段内容；把该段移到或整合进 2.3 节，并在 2.4 节只做简短回指。通过重组消除“信息有但位置不对”的问题。

### 17（PDF 页 16）

- **所选原文**：便签批注，无文本选区；锚定于 2.4.2 “Processing Data”。
- **Review 原文**：“You can also mention that every monitoring framework uses its own data formats that are different than the raw data obtained from the observation”
- **中文意思**：还可说明，各监控框架通常使用自己的数据格式，而这些格式不同于观察阶段获得的原始数据。
- **我的修改意见**：在数据处理小节明确引入“raw observation → common record → checker-specific event”三层数据模型，并说明转换器为何是架构中的必要组件。

### 18（PDF 页 16）

- **所选原文**：便签批注，无文本选区；锚定于 2.5 节 FODA/feature model 符号说明。
- **Review 原文**：“You can add that in the next chapter a feature diagram will be used so you explain the notation here.”
- **中文意思**：可以说明下一章会使用 feature diagram，所以在此处预先解释其符号。
- **我的修改意见**：在 2.5 节开头加入前向引用：“Chapter 4 uses a feature diagram to describe the monitoring design space; this section introduces the notation required to read it.” 同时确保所有图例符号均被定义。

### 19（PDF 页 17）

- **所选原文**：便签批注，无文本选区；锚定句：“each surrounding rectangle is a location (l, k, g, h), such as a machine or a robot.”
- **Review 原文**：“what is this tuple? What is the meaning of l, k, g ?”
- **中文意思**：这个元组/符号是什么？l、k、g 分别表示什么？
- **我的修改意见**：在首次出现时给出形式化定义和符号表，逐个解释位置、进程、轨迹、监视器等变量及下标；若这些字母没有后续推理价值，改用可读标签（location A、robot、server）并删除不必要符号。

### 20（PDF 页 20）

- **所选原文**：便签批注，无文本选区；锚定于列举 DDS、TCP/UDP、HTTP/WebSocket、AMQP、Kafka、MQTT 的段落。
- **Review 原文**：“references to the technologies”
- **中文意思**：需要为这些技术提供参考文献。
- **我的修改意见**：对每类技术至少引用权威规范或官方文档；可合并引用，避免每个名称都堆叠脚注。优先使用 DDS、MQTT、AMQP、Kafka 等官方规范/文档。

### 21（PDF 页 20）

- **所选原文**：便签批注，无文本选区；锚定句：“MQTT is a publish-subscribe messaging protocol...”
- **Review 原文**：“Explain why you are describing MQTT (because you will use it for the prototype)”
- **中文意思**：解释为什么在此介绍 MQTT，即因为原型实现中会使用它。
- **我的修改意见**：在 MQTT 段首加入选择动机和前向引用，说明它用于 split deployment 中机器人侧与 verifier 侧之间的传输；同时明确 MQTT 是原型选择，不是参考架构的强制依赖。

### 22（PDF 页 21）

- **所选原文**：便签批注，无文本选区；锚定于第 3 章开头：“This chapter reviews the work that is most relevant to this thesis and explains how the infrastructure developed here differs.”
- **Review 原文**：“You have not described yet what you did. May be the best is to just describe here what exists and then in the later chapters (e.g. Evaluation) you make a comparison.”
- **中文意思**：此处尚未介绍你自己的工作，不应急于比较；最好先客观描述现有工作，再在后续章节（如评价章节）进行比较。
- **我的修改意见**：第 3 章改为中性综述，只描述各方法；把“本论文如何不同/更好”的比较、架构实例化与差距验证移至第 6 章评价或第 7 章讨论。

### 23（PDF 页 21）

- **所选原文**：便签批注，无文本选区；锚定于 ROSMonitoring 小节：“A YAML file describes the topics that should be monitored.”
- **Review 原文**：“What does it mean? That this approach only observes topics? If yes, say it in the beginning”
- **中文意思**：这是什么意思？该方法是否只观察 topics？如果是，应在小节开头明确说明。
- **我的修改意见**：第一句即概括观察范围，例如：“ROSMonitoring is a topic-oriented runtime-verification framework for ROS 1.” 随后再解释插入 monitor node、YAML 配置和外部 oracle。

### 24（PDF 页 21）

- **所选原文**：便签批注，无文本选区；锚定句：“The monitor changes ROS messages into events...”
- **Review 原文**：“changes -> converts”
- **中文意思**：把 “changes” 改为更准确的 “converts”。
- **我的修改意见**：直接改为：“The monitor converts ROS messages into events and sends them to an external oracle.”

### 25（PDF 页 21）

- **所选原文**：便签批注，无文本选区；锚定于 ROSMonitoring 2.0 与消息排序讨论段落。
- **Review 原文**：“I do not understand this paragraph”
- **中文意思**：教授没有理解这一段。
- **我的修改意见**：重写为“方法事实—局限—与综述维度的关系”三句结构。不要在 related work 中混入原型设计辩护；明确 ROSMonitoring 2.0 支持什么、排序问题是什么，以及论文从该工作观察到的 gap。

### 26（PDF 页 21）

- **所选原文**：便签批注，无文本选区；锚定于 3.1 的比较维度：“which part of the system is observed, which ROS interfaces are covered, how rules are checked, what can be configured or extended, where collection and checking run...”
- **Review 原文**：“Make sure that all these are described for each related work”
- **中文意思**：确保每项相关工作都按这些维度进行描述。
- **我的修改意见**：为每个 related-work 小节采用统一模板：目标、观察对象/层级、ROS 接口、属性形式与检查器、在线/离线、部署、可配置性/可扩展性、自动化程度、局限。缺失信息明确写 “not reported”，不要凭空推断。

### 27（PDF 页 22）

- **所选原文**：便签批注，无文本选区；锚定句：“The user writes structured requirements in FRET.”
- **Review 原文**：“What is FRET?”
- **中文意思**：FRET 是什么？
- **我的修改意见**：首次出现时展开全称并用一句话定义其用途，给出原始文献/官方资料引用；同时说明它在该工作流中负责结构化需求输入，而不是运行时数据收集。

### 28（PDF 页 22）

- **所选原文**：便签批注，无文本选区；锚定句：“These requirements are translated to temporal logic and then to Copilot monitor code through Ogma.”
- **Review 原文**：“Explain Copilot and Ogma. Copilot is not the AI tool here!”
- **中文意思**：解释这里的 Copilot 和 Ogma；此处 Copilot 不是 AI 编程工具。
- **我的修改意见**：明确写为 “Copilot, a stream-based runtime-verification language/framework” 和 “Ogma, a tool that generates monitors from requirements”；给出引用，并避免仅写 Copilot 造成歧义。

### 29（PDF 页 22）

- **所选原文**：便签批注，无文本选区；锚定于 3.6 节：“It uses LTTng and tracepoints in the ROS 2 core.”
- **Review 原文**：“explain what this is or refer to a source”
- **中文意思**：解释 LTTng/tracepoints 是什么，或引用资料。
- **我的修改意见**：用一句话说明 LTTng 是低开销 Linux tracing framework、tracepoints 是代码中预定义的事件探针，并引用 ros2_tracing 与 LTTng 的官方/论文来源。

### 30（PDF 页 22）

- **所选原文**：便签批注，无文本选区；锚定句：“ros2_tracing sits below the level used in this thesis... The prototype stays with typed application data.”
- **Review 原文**：“I am confused here when you talk about levels”
- **中文意思**：教授不清楚这里所说的“层级”具体指什么。
- **我的修改意见**：定义观察层级并配一个小表：application/ROS interface level、middleware/DDS level、OS/kernel level；分别列出可见事件和工具。将 “below” 改为具体的 “middleware and OS execution level”。

### 31（PDF 页 23）

- **所选原文**：便签批注，无文本选区；锚定于 3.9 节中的 “TeSSLa specifications”。
- **Review 原文**：“what is this?”
- **中文意思**：这是什么？
- **我的修改意见**：首次出现时解释 TeSSLa 是用于事件流/时序流转换与监控的规约语言，并添加原始论文引用；说明其在该数字孪生方法中如何生成或执行监视器。

### 32（PDF 页 24）

- **所选原文**：便签批注，无文本选区；锚定于 related work 章节的总体结构。
- **Review 原文**：“General remarks about the related work: explain all abbreviations and specific terms. May be structure each subsection along some bullets: what is observed, how etc.”
- **中文意思**：对 related work 的总体意见：解释所有缩写和专业术语；可按统一要点组织每个小节，例如观察什么、如何观察等。
- **我的修改意见**：全面做缩写审计，首次出现展开；重构所有小节为统一维度。正文可用固定的小标题或紧凑表格，不一定真的用项目符号，但必须让各方法可直接横向比较。

### 33（PDF 页 24）

- **所选原文**：便签批注，无文本选区；锚定于 Table 3.1 “Comparison of selected related work”。
- **Review 原文**：“I am not sure about this table. I need a bit more detailed and more focused criteria”
- **中文意思**：当前表格不够令人信服，需要更详细、且更聚焦的比较标准。
- **我的修改意见**：重新定义与研究问题直接相关的列：observation mechanism、observable ROS entities、data representation、property formalism/checker、deployment topology、online/offline、configuration variability、generation/automation、extension mechanism。删除含糊的 “What we take from”。

### 34（PDF 页 25）

- **所选原文**：便签批注，无文本选区；锚定于 Table 3.2 的列名：“Srv. Act. Par. Life. Kernel”。
- **Review 原文**：“What is Par and the others?”
- **中文意思**：Par 等缩写分别代表什么？
- **我的修改意见**：表头使用全称或在表注中逐项定义：Services、Actions、Parameters、Lifecycle states、Kernel events；若宽度不足，将表格横向排版或用两行表头，不要依赖不透明缩写。

### 35（PDF 页 26）

- **所选原文**：便签批注，无文本选区；锚定于 Table 3.3 “Checking formalism and execution mode in related work”及其比较文字。
- **Review 原文**：“I still think that these comparisons should come later since you have explained your approach yet”
- **中文意思**：教授仍认为这些比较应放到后面，因为此时尚未解释你自己的方法。（原句语境应理解为 “have not explained”。）
- **我的修改意见**：第 3 章保留客观分类表；涉及“本论文覆盖/优于/不同于”的结论移到第 6 章或第 7 章。在介绍完参考架构后，再用相同标准进行映射比较。

### 36（PDF 页 26）

- **所选原文**：便签批注，无文本选区；锚定句：“The contribution of this thesis is this combination as one reusable infrastructure. Its novelty lies in...”
- **Review 原文**：“Do not talk about contribution here, focus on the gaps”
- **中文意思**：这里不要谈论文贡献，应专注于现有工作的缺口。
- **我的修改意见**：将该段改为 gap analysis，只陈述现有方法分别缺少哪些组合能力，不在此宣称 novelty/contribution。贡献陈述保留在第 1 章，验证性比较放到评价/讨论章节。

### 37（PDF 页 26）

- **所选原文**：便签批注，无文本选区；锚定于 related work 总结段：“The combination pursued here is passive collection from topics, service events, and action feedback/status...”
- **Review 原文**：“Can you expand this analysis a bit? May be you can put a bullet list as a summary. In the existing approaches, is there a flexibility in supporting multiple configurations, is there automation for creating the chosen solution, etc.?”
- **中文意思**：需要扩展分析，可用项目列表总结；应讨论现有方法是否支持多种配置、是否自动生成所选择的方案等。
- **我的修改意见**：用清晰的 gap 列表总结：观察对象覆盖有限、配置变体支持、组件可替换性、部署灵活性、方案生成自动化、统一数据格式、在线/离线复用。每个 gap 必须由前文表格证据支撑。

### 38（PDF 页 27）

- **所选原文**：便签批注，无文本选区；锚定于 Chapter 4 标题 “Design”。
- **Review 原文**：“I prefer a more descriptive tile. May be Towards a reference architecture for flexible monitoring?”
- **中文意思**：教授希望标题更具描述性，例如 “Towards a reference architecture for flexible monitoring”。（原文 “tile” 应为 “title”。）
- **我的修改意见**：将章标题改为 “Towards a Reference Architecture for Flexible ROS 2 Monitoring” 或更确定的 “A Reference Architecture for Configurable ROS 2 Monitoring”，并与论文最终贡献强度保持一致。

### 39（PDF 页 27）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 4.1 “Feature model of the ROS 2 monitoring infrastructure domain”。
- **Review 原文**：“The figure becomes unreadable. Either put it in landscape mode or split into two figures.”
- **中文意思**：该图难以阅读，应改成横向页面或拆成两张图。
- **我的修改意见**：优先采用横向整页图并增大字体；若仍拥挤，拆成“观察/运行维度”和“架构/实现维度”两图，正文分别引用。最终 PDF 按 100% 缩放检查最小字号。

### 40（PDF 页 27）

- **所选原文**：便签批注，无文本选区；锚定于 4.1 节 “Feature Model as Design Input”。
- **Review 原文**：“Put few more sentences why we need this model and how you obtained it (by analysing literature mainly)”
- **中文意思**：补充几句说明为什么需要该模型，以及模型如何获得（主要通过文献分析）。
- **我的修改意见**：增加方法说明：模型用于系统化监控设计空间、识别共性与变体并指导原型范围；描述从文献抽取 features、合并同义项、建立约束、迭代验证的过程，并回指第 3 章资料来源。新增的 Rabiser et al. (2019) 参考架构映射图可以作为“设计与一般监控领域模型对齐”的辅助证据，但不能替代对本论文 feature model 的具体抽取、合并和约束建立过程。

### 41（PDF 页 27）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 4.1 中 Oracle 与 Passive/Active monitoring 的关系。
- **Review 原文**：“Is Oracle also applicable to Passive mode?”
- **中文意思**：Oracle 是否也适用于被动监控模式？
- **我的修改意见**：检查 feature model 约束。若 oracle 只判断而不干预系统，它显然也适用于 passive mode，应修正模型关系并在正文说明；只有产生控制反馈的部分才属于 active monitoring。

### 42（PDF 页 27）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 4.1 中一个被建模为单选/排他的 feature 关系。
- **Review 原文**：“I think it can be both”
- **中文意思**：教授认为这里可以同时选择两者，而非只能二选一。
- **我的修改意见**：定位对应 feature 约束，将 XOR 改为 OR/可组合关系，并补充组合语义与约束；同时检查实例配置是否允许二者共同存在。

### 43（PDF 页 27）

- **所选原文**：便签批注，无文本选区；锚定句：“The concrete prototype implements one path through this map: application-level data...”
- **Review 原文**：“what is application=level here?”
- **中文意思**：这里的 “application-level” 具体是什么意思？（原文 “=” 应为连字符。）
- **我的修改意见**：定义为通过 ROS 2 topic/service/action 接口获得的带类型业务数据，并明确区别于 DDS/middleware 元数据和 OS/kernel trace events；可回指第 3 章层级表。

### 44（PDF 页 28）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 4.1/feature diagram 与 4.2 “Selected Feature Coverage” 的衔接处。
- **Review 原文**：“May be you first explain a bit how this diagram is supposed to be used. You first select a feature configuration and based on this plus additional config info you generate the infrastructure automatically. Then you describe that only part of this vision is implemented in your prototype.”
- **中文意思**：应先解释该图如何使用：先选择 feature configuration，再结合额外配置自动生成基础设施；随后说明原型只实现了这一愿景的一部分。
- **我的修改意见**：增加端到端概念流程图和四步文字：选择 features → 补充部署/参数配置 → 生成运行时配置/组件组合 → 部署执行；随后单列 “Prototype scope” 明确哪些步骤已实现、哪些仍是愿景。

### 45（PDF 页 28）

- **所选原文**：便签批注，无文本选区；锚定于 Table 4.1 的 “Parameters”。
- **Review 原文**：“I do not recall what exactly you observe about paremeters.”
- **中文意思**：教授不记得论文对 parameters 具体观察了什么。（原文 “paremeters” 为拼写错误。）
- **我的修改意见**：若原型未实现 parameter observation，将其明确列入 “Unselected/Not implemented”，并删除任何暗示已支持的表述；若已实现，则说明观察事件、数据字段、collector 和对应实验。

### 46（PDF 页 28）

- **所选原文**：便签批注，无文本选区；锚定于 Table 4.1 中自动部署/monitor placement 相关表述。
- **Review 原文**：“You should mention that this requires further configuration of the desired deployment”
- **中文意思**：应说明自动部署还需要对目标部署方式提供进一步配置。
- **我的修改意见**：区分 feature selection 与 deployment specification：features 决定能力，额外配置提供 hosts、runtime placement、transports、addresses、credentials 等。把这些作为生成器输入模式的一部分。

### 47（PDF 页 29）

- **所选原文**：便签批注，无文本选区；锚定句：“The most important one is the common record format.”
- **Review 原文**：“At this point it is not clear yet what record is. You can call it common format for the collected observations”
- **中文意思**：此处 “record” 尚未定义；可以称为 “收集到的观察数据的通用格式”。
- **我的修改意见**：首次出现改写为 “a common representation for collected observations, hereafter called a data record”，随后给出最小字段示例并前向引用 4.6 节详细 schema。

### 48（PDF 页 29）

- **所选原文**：便签批注，无文本选区；锚定于 design requirements 中的可插拔行为。
- **Review 原文**：“May be another requirements is also the ability to plug your own conversion to event format and the ability to use your own formalism for property specs and verdict service”
- **中文意思**：可新增一项需求：允许插入自定义事件格式转换，并支持用户自己的属性规约形式及 verdict service。
- **我的修改意见**：增加明确的 extensibility requirement，写成可验证的 shall statement：用户能够注册 converter 和 verdict-service plugins，使 common record 适配 checker-specific event format 与 property formalism；在评价中提供自定义插件案例。

### 49（PDF 页 29）

- **所选原文**：便签批注，无文本选区；锚定于 4.4 “Infrastructure Overview”。
- **Review 原文**：“Refer to Fig. 4.2 here and start explaining step by step. May be you can use bullets or numbering.”
- **中文意思**：这里应引用 Figure 4.2，并按步骤逐一解释；可使用项目符号或编号。
- **我的修改意见**：段首写 “Figure 4.2 provides the end-to-end dataflow”，然后按图中箭头编号说明 collect、normalize、transform、route、convert、check、export verdict；每步使用一致的组件名称。

### 50（PDF 页 29）

- **所选原文**：便签批注，无文本选区；锚定于 converter、verdict service 与 user-defined DSL 的段落。
- **Review 原文**：“explain what a DSL is and why we need this. You can say that we assume the properties to be checked are expressed in DSLs and that every verdict service may need its own data format so we need converters.”
- **中文意思**：解释 DSL 是什么以及为什么需要它；可以说明待检查属性用 DSL 表达，而不同 verdict service 可能需要自己的数据格式，因此需要 converter。
- **我的修改意见**：展开为 Domain-Specific Language，并用一段明确数据契约：property specification 属于某个 DSL，checker/verdict service 接受特定事件格式，converter 将 common records 转为该格式。给出一个具体例子。

### 51（PDF 页 29）

- **所选原文**：便签批注，无文本选区；锚定句：“Both components can be supplied as plugins.”
- **Review 原文**：“You should also explain what a plugin is, how they are developed in the context of your solution etc.”
- **中文意思**：还应解释 plugin 是什么，以及在本方案中如何开发插件等。
- **我的修改意见**：新增 “Extension/Plugin Model” 小节，定义插件接口、基类/协议、生命周期、输入输出类型、发现与 YAML 注册方式、错误处理和最小代码示例；区分 built-in components 与 user-developed plugins。

### 52（PDF 页 29）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 4.2 及 action feedback/status 的架构表述。
- **Review 原文**：“Explain also that feedback is considered in your architecture but is not implemented.”
- **中文意思**：还要说明 feedback 在架构中已被考虑，但尚未实现。
- **我的修改意见**：在架构能力、原型覆盖表和局限三处一致标注：feedback/active response 是参考架构中的扩展点，但当前 prototype 不实施从 verdict 回写系统的反馈闭环。注意区分 “action feedback observations” 与 “monitoring feedback to the system”。

### 53（PDF 页 30）

- **所选原文**：便签批注，无文本选区；锚定句：“The implementation chapter uses several role names repeatedly.”
- **Review 原文**：“why only the implementation chapter? You use them in the fig. 4.2”
- **中文意思**：为什么说这些名称只在实现章节使用？Figure 4.2 中也已经使用了它们。
- **我的修改意见**：改为 “The architecture and implementation use the following role names”，并把术语定义放在 Figure 4.2 之前或紧随图后。

### 54（PDF 页 30）

- **所选原文**：便签批注，无文本选区；锚定于 4.5 “Pipeline Roles” 中 Collector、Transformer pipeline 等定义。
- **Review 原文**：“You should explain every element, starting left and then middle bottom to top etc. All important elements should be described. Here Collector is something I do not see in the figure...”
- **中文意思**：应按图的阅读顺序解释每个元素；所有重要元素都要描述。当前文字中的 Collector 在图中似乎找不到。
- **我的修改意见**：逐一核对图与术语表，保证名称一一对应。按左到右、再按分支顺序讲解，并在图中直接标出 Collector 等角色；删除未在图中出现或未使用的定义。

### 55（PDF 页 31）

- **所选原文**：便签批注，无文本选区；锚定于 “docs/datarecord_spec.md”。
- **Review 原文**：“where is this folder? You have not explained. You can put the schema or an example in an appendix”
- **中文意思**：这个文件夹在哪里？前文没有解释。可以把 schema 或示例放到附录。
- **我的修改意见**：不要只给仓库内相对路径。正文简述 schema，附录给完整 JSON/YAML 示例和字段定义；同时给出公开仓库的可点击 URL，并说明该文件在仓库中的路径。

### 56（PDF 页 31）

- **所选原文**：便签批注，无文本选区；锚定于 Table 4.2 的 `data`、`metadata` 等字段说明。
- **Review 原文**：“These are not clear to me”
- **中文意思**：这些字段/说明对教授而言不清楚。
- **我的修改意见**：把抽象字段描述改成类型化 schema：字段名、类型、必选性、语义、按 record type 的允许值，并配一个真实 topic record 示例。尤其避免 “depending on type” 而不列出各类型。

### 57（PDF 页 31）

- **所选原文**：便签批注，无文本选区；锚定于字段 `data`：“Contains the monitoring configuration, captured payload, session statistics, or error details, depending on type.”
- **Review 原文**：“This is actually pretty crucial. How do you represent the payload with all possible data types, nesting etc. I expect this to be clarified in the text”
- **中文意思**：这是关键问题：如何表示包含各种数据类型、嵌套结构等的 payload？正文必须澄清。
- **我的修改意见**：专门解释 ROS 2 typed message 到可序列化结构的转换规则：primitive、array/sequence、nested message、bounded types、byte data、time/duration、NaN/Inf 等；说明类型信息是否保留、JSON 限制、深度/大小和错误处理，并用嵌套消息示例验证。

### 58（PDF 页 32）

- **所选原文**：便签批注，无文本选区；锚定于 topic/service/action 统一 record 身份字段的段落。
- **Review 原文**：“I recommend to include an example”
- **中文意思**：教授建议加入示例。
- **我的修改意见**：给出至少一个完整 data record；最好并列 topic、service event、action feedback 三个精简 JSON 示例，突出共同字段和 source-specific metadata。

### 59（PDF 页 32）

- **所选原文**：便签批注，无文本选区；锚定句：“The same pipeline can run in two main deployment forms. They are the concrete instances...”
- **Review 原文**：“what are they?”
- **中文意思**：“它们”具体指什么？
- **我的修改意见**：消除代词，直接命名：“The integrated and split deployments are two concrete instances of ...”，并在首次出现时各用一句定义。

### 60（PDF 页 32）

- **所选原文**：便签批注，无文本选区；锚定句：“It corresponds to the traditional organisation in Figure 2.7...”
- **Review 原文**：“Is this mentioned in 2.6.1 as integrated deployment?”
- **中文意思**：2.6.1 中是否已经把这种形式称为 integrated deployment？
- **我的修改意见**：统一第 2 章与第 4 章术语。若 2.6.1 只使用 “traditional/centralized”，在那里加入映射：“called integrated deployment in this thesis”，或全篇统一为同一术语。

### 61（PDF 页 32）

- **所选原文**：便签批注，无文本选区；锚定短语：“one ROS 2-facing process”。
- **Review 原文**：“what is ROS2-facing?”
- **中文意思**：“ROS2-facing” 是什么意思？
- **我的修改意见**：避免自造术语，改为 “a process that participates in the ROS 2 graph and uses ROS 2 APIs to collect observations”；若多次使用，首次定义后再简写为 ROS 2-facing。

### 62（PDF 页 32）

- **所选原文**：便签批注，无文本选区；锚定于 integrated deployment 中 collection、processing、checking、output 与 process 的关系。
- **Review 原文**：“so you have multiple processes? Is this always the case that the se items runs in separate processes?”
- **中文意思**：这里是否有多个进程？这些组件是否总是在独立进程中运行？
- **我的修改意见**：明确区分 logical components、ROS nodes、OS processes 与 hosts，给出部署映射表。说明 integrated 模式中哪些角色共进程，split 模式中哪些被分隔，以及配置是否允许进一步拆分。

### 63（PDF 页 32）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 4.3 的 UML deployment 表示和正文 “process”。
- **Review 原文**：“Strictly speaking process is not a part of the deployment diagram UML notation”
- **中文意思**：严格来说，process 并不是 UML deployment diagram 的标准元素。
- **我的修改意见**：使用标准 UML 元素（node/device、execution environment、artifact、component）并正确应用 stereotype；若坚持画进程，明确声明这是非严格 UML 的自定义部署视图并给出图例。

### 64（PDF 页 32）

- **所选原文**：便签批注，无文本选区；锚定于仅定义 integrated 和 split 两种部署。
- **Review 原文**：“But I think you can support much more scenarios for deployment. Why only two are defined here?”
- **中文意思**：架构似乎能支持更多部署场景，为什么这里只定义两种？
- **我的修改意见**：说明这两种是 prototype/evaluation configurations，而非架构支持的全部拓扑；先描述一般 placement variability，再列举可能场景，最后解释为何选择这两种代表性实例进行实现与评价。

### 65（PDF 页 32）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 4.3 “Integrated deployment topology”。
- **Review 原文**：“do you refer to this figure from the text?”
- **中文意思**：正文是否引用了这张图？
- **我的修改意见**：在图前明确加入 “Figure 4.3 shows the integrated deployment topology”，并在图后解释关键映射；全文运行一次图表交叉引用检查。

### 66（PDF 页 32）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 4.4 “Split deployment topology”。
- **Review 原文**：“Why fig. 4.4 is not explained”
- **中文意思**：为什么 Figure 4.4 没有得到解释？
- **我的修改意见**：新增一段按机器人侧、传输边界、verifier 侧解释 Figure 4.4，说明 record 在何处转换/传输、哪些组件共进程、网络与时钟假设，以及它与 Figure 2.x 一般组织形式的对应关系。

### 67（PDF 页 33）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 4.4 中某个 UML 符号/表示法。
- **Review 原文**：“This is usually used to denote interface”
- **中文意思**：该符号通常用于表示 interface。
- **我的修改意见**：核对教授所指符号，若当前被用于数据流、端口或组件，应换成正确 UML 记法；在图例中明确箭头、接口和部署依赖的语义，避免混用。

### 68（PDF 页 33）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 4.5 “Runtime sequence from collection to verdict export”。
- **Review 原文**：“I would move this figure before the deployment”
- **中文意思**：教授建议把该图移到部署图之前。
- **我的修改意见**：先展示与部署无关的 logical/runtime sequence，再展示它如何映射到 integrated 和 split topology；调整编号、交叉引用和过渡段。

### 69（PDF 页 33）

- **所选原文**：便签批注，无文本选区；锚定于第 4 章结尾。
- **Review 原文**：“Put a short conclusion section that summarizes the main points in this chapter”
- **中文意思**：增加一个简短结论小节，总结本章要点。
- **我的修改意见**：新增 “Chapter Summary”，用一段回顾 feature model、selected scope、requirements、reference architecture、data model 和 deployment variability，并自然引出第 5 章实现。

### 70（PDF 页 34）

- **所选原文**：便签批注，无文本选区；锚定句：“The repository separates infrastructure code from project-specific checking logic.”
- **Review 原文**：“I would prefer to have a separate section about code organization. Now you talk about repository but I do not know what this is.”
- **中文意思**：最好单设代码组织小节；目前突然谈 repository，但读者还不知道它指什么。
- **我的修改意见**：新增 “Implementation and Repository Organization” 小节，先给公开仓库 URL、顶层目录树和各目录职责，再讨论 `monitor/`、`custom/` 等包；将此内容从依赖/运行时介绍中分离。

### 71（PDF 页 35）

- **所选原文**：便签批注，无文本选区；锚定于配置生成器与 monitor process 的说明之间。
- **Review 原文**：“I would first expect to see a diagram with the transformation chain. You have specification files that are used to generate stuff. Then show the pipeline.”
- **中文意思**：应先看到一张转换链图：输入是 specification files，经过生成后得到相应产物，然后再展示运行管线。
- **我的修改意见**：在实现章开头加入两层总览图：设计/部署 specification → config generator → per-runtime YAML；随后 YAML → runtime construction → observation/checking pipeline。明确区分生成时与运行时。

### 72（PDF 页 35）

- **所选原文**：便签批注，无文本选区；锚定于 5.2 “The Monitor Process” 的启动流程。
- **Review 原文**：“Put a figure and then explain it.”
- **中文意思**：先放一张图，再据图进行解释。
- **我的修改意见**：增加 monitor runtime component diagram 或启动顺序图，标出 YAML loader、typed config、collector、transformer、dispatcher、checker、exporter；正文按图中编号解释，减少纯文字堆叠。

### 73（PDF 页 38）

- **所选原文**：便签批注，无文本选区；锚定于 5.7 “Configuration and Graph Wiring”。
- **Review 原文**：“I am lost here. What is the purpose of this section? What do you want to explain?”
- **中文意思**：教授在这里失去上下文，不清楚本节目的和要说明的内容。
- **我的修改意见**：在节首增加目标句：本节解释一份 runtime YAML 如何选择组件并连接 checking graph。先给完整示例和结构图，再分为 schema、component resolution、links/graph construction 三个小节。

### 74（PDF 页 38）

- **所选原文**：便签批注，无文本选区；锚定短语：“One YAML file configures one runtime.”
- **Review 原文**：“what is runtime? I remember we discussed it but you do not explain it here.”
- **中文意思**：什么是 runtime？之前讨论过，但正文此处没有解释。
- **我的修改意见**：在第 4 章或第 5 章首次出现时定义：“A runtime is one executable instance that hosts a configured set of monitoring roles.” 同时给出 monitor runtime 与 runner/verifier runtime 的区别及其与 process/host 的映射。

### 75（PDF 页 39）

- **所选原文**：便签批注，无文本选区；锚定句：“The links section defines the checking graph.”
- **Review 原文**：“what is checking graph?”
- **中文意思**：什么是 checking graph？
- **我的修改意见**：定义 checking graph 为由 source/input、converter、verdict service、output 等节点及其有向数据流边组成的配置图；给出一张三节点示例图并说明允许的边、分支、拓扑约束和执行语义。

### 76（PDF 页 39）

- **所选原文**：便签批注，无文本选区；锚定于 runner process、input、converter 和 verdict service 的段落。
- **Review 原文**：“I do not understand this section!”
- **中文意思**：教授没有理解这一节。
- **我的修改意见**：从读者任务出发重写：runner 是什么、何时使用、输入来自哪里、内部可以承载什么、输出去哪里。配 integrated/split 两个最小 YAML 和部署图，不要一次引入 relay 等高级变体。

### 77（PDF 页 39）

- **所选原文**：便签批注，无文本选区；锚定于 5.9 “Generating Deployment Configurations” 之前。
- **Review 原文**：“Before this I need a clear picture how an implementation of a particular monitoring infra looks like: how many YAML files, library python files, user-developed files etc. are present. Only then it will become clear what you try to do here”
- **中文意思**：在此之前，需要清楚展示一个具体监控基础设施实例由什么组成：多少 YAML、库 Python 文件、用户开发文件等；之后生成过程才容易理解。
- **我的修改意见**：增加 “Anatomy of a Monitoring Solution” 图/表，以 integrated 和 split 各给一个实例：用户编写的 deployment spec、property spec、converter/verdict plugin，框架提供的库，以及生成的每主机 YAML。标注 authored/generated/reused。

### 78（PDF 页 40）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 5.1 “Data model used by the configuration generator”。
- **Review 原文**：“Refer to this picture when explaining the structure”
- **中文意思**：解释结构时应明确引用这张图。
- **我的修改意见**：在图前加入交叉引用，按 Figure 5.1 中 generation request → hosts → runtimes/observables → links 的层级讲解；避免图与正文各自独立。

### 79（PDF 页 40）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 5.1 中 “generation request” 的名称。
- **Review 原文**：“I do not liek this name. It is a configuration”
- **中文意思**：教授不喜欢这个名称；它本质上是一个 configuration。（原文 “liek” 为拼写错误。）
- **我的修改意见**：将 `generation request` 重命名为 `deployment specification` 或 `deployment configuration`，同步更新数据类、算法、图、示例和全文术语。

### 80（PDF 页 40）

- **所选原文**：便签批注，无文本选区；锚定句：“The following example places a monitor next to the robot...”
- **Review 原文**：“what does it mean next to the robot? Running on the robot?”
- **中文意思**：“next to the robot” 是什么意思？是否指运行在机器人上？
- **我的修改意见**：用精确部署术语替换：若在机器人计算机上运行，写 “runs on the robot-side host”；若只是同一网络/地点，明确说明物理和逻辑位置。

### 81（PDF 页 40）

- **所选原文**：便签批注，无文本选区；锚定句：“Algorithm 1 shows the projection used by the generator.”
- **Review 原文**：“what is projection?”
- **中文意思**：“projection” 在这里是什么意思？
- **我的修改意见**：不用未定义的数学术语。改为 “conversion/generation procedure”，或明确定义为将全局 deployment specification 按 host 分解为各 runtime configuration 的映射。

### 82（PDF 页 41）

- **所选原文**：便签批注，无文本选区；锚定于 Algorithm 1 标题：“Project a deployment request into runtime YAML files”。
- **Review 原文**：“Instead of Project, use convert or generate. What you do here is generation of YAML config files from a deployment spec.”
- **中文意思**：不要用 Project，应使用 convert 或 generate；这里做的是从 deployment spec 生成 YAML 配置文件。
- **我的修改意见**：算法标题改为 “Generate runtime YAML configurations from a deployment specification”，并将正文中的 project/projection 全部替换为 generate/generation。

### 83（PDF 页 43）

- **所选原文**：便签批注，无文本选区；锚定于 RQ4：“support the monitoring needs of realistic ROS 2 applications”及五个 experiments。
- **Review 原文**：“How do you know that these examples are realistic?”
- **中文意思**：如何证明这些例子具有现实性？
- **我的修改意见**：为 case selection 提供依据：来源于代表性 ROS 2 通信模式、Nav2/多机器人用例、文献或工业需求；建立 “realistic needs → experiment” 映射，并避免无证据地使用 realistic，可改为 representative。

### 84（PDF 页 43）

- **所选原文**：便签批注，无文本选区；锚定于评价章节实验概览。
- **Review 原文**：“Apart from these experiments, I remember you checked if the existing approaches can be instantiated with your architecture. I think it is a good idea to include this as well.”
- **中文意思**：除这些实验外，之前还检查了现有方法能否由该架构实例化；建议把这项评价也纳入论文。
- **我的修改意见**：新增 architecture expressiveness/case reconstruction 评价：从第 3 章选若干代表性方法，将其组件、数据流、部署和检查方式映射到参考架构，明确 fully/partially/not representable 及原因。新加入的 ROSMonitoring、ROMoSu 和 Digital-Twin RV 三张映射图正好可以成为该评价的原始材料；但最终论文必须把黄色箭头升级为带语义和状态的映射表，并将三者分别判定为“部分可表示”，不能笼统声称完整实例化。

### 85（PDF 页 43）

- **所选原文**：便签批注，无文本选区；锚定于 Chapter 6 “Evaluation” 开头。
- **Review 原文**：“Overall observation so far: I still miss a clear and simple explanation what steps I need to follow to specify and obtain a monitoring infrastructure”
- **中文意思**：总体而言，仍缺少一个清楚、简单的说明：用户需要遵循哪些步骤来规约并获得一个监控基础设施。
- **我的修改意见**：这是核心结构问题。增加贯穿全文的用户工作流：选择需求/features → 编写 property 与 deployment spec → 选择/开发 plugins → 运行 generator → 部署 runtimes → 收集 verdicts。设计章给概念流程，实现章给文件/命令，评价章逐实验报告每步产物。

### 86（PDF 页 44）

- **所选原文**：便签批注，无文本选区；锚定于 E1 deployment 描述。
- **Review 原文**：“You simulate in Gazebo, right?”
- **中文意思**：这里是在 Gazebo 中仿真，对吗？
- **我的修改意见**：明确写出仿真环境、机器人/节点、Gazebo 版本和执行方式；若 E1 不使用 Gazebo，也应直接说明测试数据如何产生，消除歧义。

### 87（PDF 页 44）

- **所选原文**：便签批注，无文本选区；锚定于 E1 的 rule、results 和生成 verdict 描述。
- **Review 原文**：“I think it is important to describe how the framework was used. What did you specify, what was generated, what was manually created? This is valid for all experiments.”
- **中文意思**：必须说明每个实验如何使用框架：哪些由用户规约、哪些由框架生成、哪些手工创建；这适用于所有实验。
- **我的修改意见**：给每个实验增加统一的 “Framework usage” 表：input specifications、selected built-ins、user-written plugins/property files、generated YAML/artifacts、manual deployment steps、reused framework code。

### 88（PDF 页 44）

- **所选原文**：便签批注，无文本选区；锚定于 Table 6.3：“Expected / produced verdicts 40 / 40; Missed or additional verdicts 0.”
- **Review 原文**：“were there failures? Were the resuts as expected?”
- **中文意思**：是否出现失败？结果是否符合预期？（原文 “resuts” 为拼写错误。）
- **我的修改意见**：明确给出 pass/fail criterion、observed failures、unexpected records/verdicts 和结论；不要只列计数，应写 “E1 passed the predefined correctness criterion...”。

### 89（PDF 页 45）

- **所选原文**：便签批注，无文本选区；锚定于 E2 增加 service/action observations 的段落。
- **Review 原文**：“Btw I still miss a good explanation how you get grip on services and actions?”
- **中文意思**：仍缺少清楚说明：框架到底如何捕获/观察 services 和 actions？
- **我的修改意见**：增加专门技术小节和序列图：service introspection 如何启用、请求/响应事件 topic 与关联字段；action 如何由 goal/result/cancel services、feedback/status topics 构成，当前具体收集哪些、遗漏哪些。

### 90（PDF 页 45）

- **所选原文**：便签批注，无文本选区；锚定句：“The speed rule runs both inside the monitor and inside the verifier; the reset rule runs in the verifier.”
- **Review 原文**：“why?”
- **中文意思**：为什么要这样部署/重复运行这些规则？
- **我的修改意见**：说明实验设计理由：例如比较 integrated 与 split 结果一致性、验证 transport boundary，或建立本地基准。如果没有明确研究目的，删除重复 checker，简化实验。

### 91（PDF 页 52）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 6.5 中 Raspberry Pi 上的 “reference node_runner / same three checks”。
- **Review 原文**：“what is this?”
- **中文意思**：图中的这个 reference node_runner/参考检查实例是什么？
- **我的修改意见**：在图例和正文中定义它是仅用于实验对照的 Pi-local verifier，说明输入、运行的三个 checks、与 Mac verifier 的比较目的；可将名称改为 “Pi-local reference verifier”。

### 92（PDF 页 52）

- **所选原文**：便签批注，无文本选区；锚定于 Figure 6.5 中指向 Pi-local reference verifier 的虚线。
- **Review 原文**：“what is the meaning of the dashed line here?”
- **中文意思**：图中虚线表示什么？
- **我的修改意见**：在图注/图例明确：“Dashed elements denote the experimental reference path, not the primary deployment.” 同时标注虚线承载的是 MQTT records 还是逻辑依赖。

### 93（PDF 页 55）

- **所选原文**：便签批注，无文本选区；锚定于 6.7 节资源使用与延迟的一段数字结果。
- **Review 原文**：“I think it is a good idea to put these into a table”
- **中文意思**：建议把这些结果整理成表格。
- **我的修改意见**：用表格列出 experiment、host、sources、CPU、memory、record-to-verdict latency、network mode，并写清均值/中位数/百分位、样本量与测量方法。

### 94（PDF 页 55）

- **所选原文**：便签批注，无文本选区；锚定于 6.8 “Answer to RQ4”。
- **Review 原文**：“This evaluation is OK but as I mentioned, we also need to show that the framework saves us work. It is therefore important to mention how the framework was used and to show that you had to implement less compared to a situation that you do not use the framework”
- **中文意思**：当前评价可以，但还必须证明框架节省了工作；说明框架如何使用，并展示相较不用框架时需要实现得更少。
- **我的修改意见**：新增 effort/automation evaluation。定义 baseline 手工方案，比较 user-written LOC/files、配置量、重复组件、实施步骤或时间；区分框架已有代码、生成代码和用户代码，并讨论 LOC 指标局限。

### 95（PDF 页 55）

- **所选原文**：便签批注，无文本选区；锚定于 Table 6.11 的 “monitoring needs” 行列。
- **Review 原文**：“How did you come up with these needs? It is good to formulate them in the beginning so that we need to know what is evaluated.”
- **中文意思**：这些 monitoring needs 是如何得出的？应在评价开头先提出，读者才能知道将评价什么。
- **我的修改意见**：在第 6 章开头定义评价需求/criteria，并追溯到 RQ、feature model、related-work gaps 和 case-study requirements；随后建立 criterion → experiment → metric 的可追踪矩阵。

### 96（PDF 页 55）

- **所选原文**：便签批注，无文本选区；锚定于 6.8 的评价总结。
- **Review 原文**：“As an additional evaluation, you can include the slides you prepared before that show that the reference architecture is capable to handle the existing approaches”
- **中文意思**：可把之前幻灯片中“参考架构能够容纳现有方法”的分析加入额外评价。
- **我的修改意见**：将幻灯片内容转为正式、可复查的架构映射表；对每个现有方法说明组件和连接如何映射、需要哪些 feature configuration，以及无法映射的部分。当前四张新图已经覆盖 ROSMonitoring、ROMoSu、Digital-Twin RV 和 Rabiser et al. 的通用参考架构，可作为新增评价小节的素材；建议把前三张作为 concrete approach reconstruction，把 Rabiser 图单独作为 general-domain alignment。

### 97（PDF 页 58）

- **所选原文**：便签批注，无文本选区；锚定于 7.1.3 “Design Trade-offs” 之前的 Discussion 内容。
- **Review 原文**：“Up to here I would keep the text but structure it differently. I suggest to organize it as answers to research questions.”
- **中文意思**：到此为止的内容可以保留，但应换一种结构，建议按研究问题的回答来组织。
- **我的修改意见**：将 Discussion 主体重组为 RQ1-RQ4 四个小节，每节采用 evidence → answer → interpretation → limitations；把跨 RQ 的 trade-offs 与 limitations 单列，避免按实验流水账复述。

### 98（PDF 页 58）

- **所选原文**：便签批注，无文本选区；锚定于 7.1.3 “Design Trade-offs”。
- **Review 原文**：“classify the trade-offs and put them in bullet list”
- **中文意思**：对 trade-offs 分类，并用项目列表呈现。
- **我的修改意见**：按维度分类：data reduction vs fidelity、local vs remote checking、generality vs checker-specific adaptation、automation vs configuration complexity、passive observation vs coverage、online latency vs replayability。每条写 benefit、cost、适用条件和实验依据。

### 99（PDF 页 58）

- **所选原文**：便签批注，无文本选区；锚定于 plugin interfaces、converter 与 verdict service 的段落。
- **Review 原文**：“Just to remind you that this plugin story remains unclear to me”
- **中文意思**：再次提醒，plugin 的整体设计和使用方式仍不清楚。
- **我的修改意见**：将其列为高优先级重写项，而非只补一句定义。用一个端到端插件实例展示接口代码、输入输出、property DSL、YAML 注册、加载过程、错误情况和运行结果；统一 plugin/component/adapter/service 术语。

### 100（PDF 页 60）

- **所选原文**：便签批注，无文本选区；锚定于 7.3 “Threats to Validity”。
- **Review 原文**：“The threats are usually classified as internal and external”
- **中文意思**：有效性威胁通常分为 internal 和 external。
- **我的修改意见**：至少按 internal/external validity 重组；若学院规范允许，可进一步用 construct、internal、external、conclusion validity。每项写 threat、可能影响和 mitigation。

### 101（PDF 页 60）

- **所选原文**：便签批注，无文本选区；锚定于 related work/feature model 覆盖范围的有效性威胁。
- **Review 原文**：“One threat is that you might have missed related work”
- **中文意思**：一个重要威胁是可能遗漏相关工作。
- **我的修改意见**：把 literature incompleteness 列为 external/construct threat，报告检索数据库、关键词、时间范围、纳入排除标准、snowballing 和工业工具覆盖；承认非系统综述的限制。

### 102（PDF 页 60）

- **所选原文**：便签批注，无文本选区；锚定于 7.4 “Future Work”。
- **Review 原文**：“Clearly, many things can be done in the future. Again I suggest to organize the section in bullet list”
- **中文意思**：未来可做的事情很多，建议再次用项目列表组织。
- **我的修改意见**：按主题分组列出 future work：observation coverage、active feedback、deployment/configuration generation、plugin ecosystem、ordering/time semantics、scalability/industrial validation。每项简述动机与优先级。

### 103（PDF 页 62）

- **所选原文**：便签批注，无文本选区；锚定于 8.1 “Answers to the Research Questions”。
- **Review 原文**：“OK, you can give the answers here as well. Just make sure to avoid duplication with the Discussion section”
- **中文意思**：可以在结论中再次回答研究问题，但要避免与 Discussion 重复。
- **我的修改意见**：Discussion 给证据、解释与限制；Conclusion 每个 RQ 只给 2-4 句最终答案，不重复表格、实验细节和完整论证。

### 104（PDF 页 62）

- **所选原文**：便签批注，无文本选区；锚定于 RQ1-RQ4 的答案标题。
- **Review 原文**：“Just repeat the questions here”
- **中文意思**：在这里直接再次写出各研究问题的完整文本。
- **我的修改意见**：每个小节先逐字重述 RQ，再紧接简洁答案；确保问题文本与第 1 章完全一致，可使用统一 LaTeX 命令避免版本漂移。

### 105（PDF 页 64）

- **所选原文**：便签批注，无文本选区；锚定于 8.3 “Future Work”。
- **Review 原文**：“This is a duplication with the previous chapter. Move all future work in one place”
- **中文意思**：这与上一章重复；把所有 future work 集中放在一个位置。
- **我的修改意见**：二选一：保留第 7 章完整 Future Work，结论只用一句回指；或将完整列表移到第 8 章并从 Discussion 删除。建议保留在 Conclusion 末尾，更符合读者预期。

### 106（PDF 页 69）

- **所选原文**：便签批注，无文本选区；锚定于 Appendix A 空白/占位页。
- **Review 原文**：“Can you please put all case studies in a repo and put a link to this repo? Also all the implementation work”
- **中文意思**：请把所有 case studies 和全部实现工作放入一个代码仓库，并在论文中给出链接。
- **我的修改意见**：整理可公开复现仓库，包含 source、case studies、configs、plugins、data/expected outputs、运行说明、依赖版本和许可证；在论文的 artifact/reproducibility 小节及附录提供永久链接，最好附 release tag/DOI。

## 新增四张架构映射图的适用性评估

### 总体判断

这四张图与教授 review **明确相关**，最直接回应：

- **Review 84**：把“现有方法能否由本论文参考架构实例化”加入评价。
- **Review 96**：把之前幻灯片中的架构映射分析正式写入论文。

它们还可以辅助回应 Review 33、37（采用更聚焦的比较标准并扩展 gap analysis）、Review 40（说明设计与文献分析的关系）、Review 44（解释架构/feature configuration 如何使用）、Review 49、54（按步骤和元素解释架构图）以及 Review 9（为复用图片提供来源）。

但是，这些图目前只能作为**分析草图**。黄色箭头表达了作者认为存在的对应关系，却没有区分：

- 精确对应；
- 需要 adapter/plugin 才能对应；
- 只在参考架构层面支持、当前 prototype 未实现；
- 本论文架构尚不能表示。

如果直接用它们证明 “the reference architecture can handle the existing approaches”，论证会过强。最终评价应使用 `fully represented / partially represented / not represented`，并分别说明 architecture-level support 与 prototype-level support。

### 1. ROSMonitoring 映射图

文件：[Compare with ROSMonitoring.png](<../diagrams/Compare with ROSMonitoring.png>)

**适用结论：适用，但只能判为“部分可表示”。**

根据 [ROSMonitoring 原论文](https://iris.unige.it/bitstream/11567/1035245/1/ROSMonitoring_ICRA2020.pdf)，其核心流程是：用户编写 YAML；generator 自动生成 monitor node 并修改 ROS launch/remapping；monitor 截获或旁路观察 topic message；ROS message 转为 JSON；online 模式通过 WebSocket 调用外部 oracle，offline 模式写日志供后续检查；oracle 返回 verdict，在线 filter 模式还可以阻止或重新发布消息。

较可靠的映射为：

| ROSMonitoring 元素 | 本论文参考架构元素 | 判定 |
|---|---|---|
| `config.yaml` | Monitor configuration / deployment specification | 直接对应，但 schema 不同 |
| instrumentation generator | Build/generation step | 部分对应；本论文当前主要生成 YAML，并不修改 ROS launch files |
| generated `monitor.py` | Monitor Runtime + Collector | 部分对应 |
| ROS topic messages | ROS 2 Runtime / Topics | 概念对应；原论文主要针对 ROS 1 |
| ROS-to-JSON conversion | common record construction / Data Converter | 部分对应，需区分“观察规范化”和“checker-specific conversion” |
| WebSocket oracle boundary | Transport Broker + Verdict Service | 直接的架构级对应 |
| `log.txt` / offline checking | Evidence Runtime + Replay/Offline checking | 架构级对应 |
| oracle specification | Property/DSL plugin configuration | 直接的概念对应 |

主要缺口：

1. ROSMonitoring 的默认特色是对通信路径进行 instrumentation/remapping，并可主动 filter 消息；本论文当前 prototype 以被动观察为主。
2. 原论文的 monitor 能依据 oracle verdict 决定是否重新发布消息，这要求 Feedback Runtime 或 active proxy；教授已要求明确写出 feedback 在架构中考虑但未实现。
3. ROSMonitoring 自动生成 monitor code 和修改 launch files，而本论文生成的是 deployment/runtime YAML，二者不能画成完全等价。
4. 原图中的 ROS 1 nodes 不应直接标成“ROS 2 已实现支持”，需要注明这是概念映射。

**建议用于论文的位置**：评价章新增 “Architecture Reconstruction: ROSMonitoring”。正文用表格说明映射，图只做视觉总览；结论写成 “The reference architecture represents the main observation-to-oracle path, while invasive instrumentation and verdict-driven message filtering require an active proxy/feedback extension that is not implemented in the prototype.”

### 2. ROMoSu 映射图

文件：[Compare with ROMoSu.png](<../diagrams/Compare with ROMoSu.png>)

**适用结论：适用，而且是四张图中最适合作为架构覆盖案例之一；仍应判为“部分可表示”。**

根据 [ROMoSu 原论文](https://rose-workshops.github.io/files/rose2023/papers/RoSE2023_paper_3.pdf)，ROMoSu 区分 Monitoring Configuration 与 Monitoring Data Collection 两个阶段，使用可复用的 Mon-Config 和 SuM-Type；其架构包含 Admin UI、Framework Core、ROS Connector/Adaptation Manager、Runtime Data Broker、Runtime Data Validation、Persistence 和 Dashboard。外部 constraint engine、database 等服务通过 broker 接入。

较可靠的映射为：

| ROMoSu 元素 | 本论文参考架构元素 | 判定 |
|---|---|---|
| Mon-Config / SuM-Type / Config Editor | User Settings + Monitor Config | 部分对应 |
| ROS Connector / Adaptation Manager | ROS Runtime + Collectors | 部分对应 |
| topic field selection / publishing frequency | Filters / Transformers | 直接的功能对应 |
| Runtime Data Broker | Exporter + Transport Broker | 直接对应 |
| Runtime Data Validation | Data Converter + Verdict Service | 部分对应 |
| Runtime Data Persistence | Evidence Runtime / Database | 直接对应 |
| Dashboard / Data Explorer | Evidence Runtime / Dashboard API | 架构级对应 |
| external services | plugins or downstream services | 架构级对应 |

主要缺口：

1. ROMoSu 提供 Admin UI、system inspection、configuration database、runtime cache、动态 activation/update/delete；这些属于 management/control plane，本论文图中没有等价的完整子系统。
2. ROMoSu 的可复用对象是 Mon-Config 和 SuM-Type，而本论文的 deployment specification、runtime YAML 与 plugin registry 语义不同。
3. ROMoSu 主要是 topic-oriented ROS monitoring；本论文额外关注 ROS 2 service/action observations 和 split verification，但这些是差异，不应被画成 ROMoSu 本身的能力。
4. Dashboard 和 persistence 是 ROMoSu 的实际组件；若本论文只是架构中预留接口、prototype 未实现，应明确标成 architecture-only。

**建议用于论文的位置**：作为 “mostly representable monitoring data path, partially representable management plane” 的案例。它还能帮助教授理解本论文与 ROMoSu 的真正差异：不是简单重复 broker/collector，而是数据记录、checker adapter、ROS 2 异构观察和 deployment generation 的侧重点不同。

### 3. Digital Twin Enabled Runtime Verification 映射图

文件：[compare with Digital Twin Enabled Runtime Verification.png](<../diagrams/compare with Digital Twin Enabled Runtime Verification.png>)

**适用结论：可以使用，但必须明确为“监控子路径可表示，完整 Digital Twin 闭环不可由当前架构完整表示”。**

根据 [Digital Twin Enabled Runtime Verification 原论文](https://arxiv.org/abs/2412.09913)，机器人状态通过 MQTT 发送到 cloud-located digital twin；数字孪生保存并扩展状态，运行由 TeSSLa property 生成的 monitors，通过 runtime validation 影响机器人是否执行 actuation。论文还区分 monitor 集成到 DT、作为 private service、作为 public/common service 等模式，并强调 property 外部化。

较可靠的映射为：

| Digital-Twin RV 元素 | 本论文参考架构元素 | 判定 |
|---|---|---|
| robot/environment runtime data | ROS 2 Runtime + Collectors | 部分对应 |
| MQTT broker | Transport Broker / MQTT | 直接对应 |
| data storage | Evidence Runtime / Database | 直接对应 |
| TeSSLa input preparation | Data Converter | 直接的职责对应 |
| TeSSLa monitor | Verdict Service / DSL-specific checker | 直接的职责对应 |
| externalized monitor properties | Property/DSL plugin configuration | 直接的概念对应 |
| validation result returned to robot | Feedback Runtime | 架构级对应、prototype 未实现 |
| monitor as private/public DT service | deployment/placement variation | 部分对应 |

不能直接等同的内容：

1. Digital Twin 的 State、Behaviors、Models、Simulators、Operations 和 goal orchestration 不是普通 Evidence Runtime，也不能全部塞进 Verdict Service。
2. 该方案执行 Sense–Analyze–Validate–Execute 闭环，verdict 会影响 actuation；本论文 prototype 没有实现此 active feedback。
3. DT state 不只是原始 ROS observation，还包含模型推导状态和仿真结果；本论文 common record 若只表达观察数据，不能宣称完整表示该语义。
4. 若将整个 Digital Twin 当成一个外部 composite service/plugin，可以表示接口连接，但这只能证明架构可集成外部 DT 服务，不能证明架构内部覆盖了 DT 架构。

**建议用于论文的位置**：作为 boundary case。它比“完全实例化成功”的案例更有价值，因为它能清楚展示参考架构的边界：基础 observation–transport–conversion–checking–feedback path 可映射，但 DT-specific state/model/behavior subsystem 是外部服务或架构扩展。

### 4. Rabiser et al. (2019) 通用监控参考架构映射图

文件：[Map to A domain analysis of resource and requirements monitoring(2019).png](<../diagrams/Map to A domain analysis of resource and requirements monitoring(2019).png>)

**适用结论：非常适合支持设计依据与通用领域对齐，但不应与前三张“具体方法实例化”混为一类。**

[Rabiser et al. (2019)](https://doi.org/10.1016/j.infsof.2019.03.013) 通过系统分析 47 个 resource/requirements monitoring approaches 得到 domain model 和 reference architecture，并用 5 个 monitoring solutions 对参考架构进行实例化验证。其三大区域是 Monitoring Setup、Monitoring Execution、Monitoring Support；核心职责包括 monitoring definition、instrumentation/probes、collection、filtering/aggregation/transformation、routing、checking 和 persistency。

较可靠的映射为：

| Rabiser 参考架构元素 | 本论文参考架构元素 | 判定 |
|---|---|---|
| Monitoring Definition | Monitor Config + Plugin/Property specifications | 部分对应 |
| Instrumentation Support / Probe | Build/generation + Collectors | 部分对应；本论文未实现通用 probe insertion |
| Monitoring Information Collection | ROS 2 Runtime + Collectors | 直接对应 |
| Filtering / Aggregation / Transformation | Filters/Transformers + Data Converter | 直接或部分对应 |
| Routing / Distribution | Exporters + Transport Broker | 直接对应 |
| Checking | Verdict Service | 直接对应 |
| Persistency | Evidence Runtime / Database | 架构级对应 |
| Application/Support layer | Dashboard API / Feedback/external applications | 部分对应 |

这张图可以证明本论文架构覆盖了一般监控 reference architecture 的主要职责，并把 ROS 2 interfaces、checker adapters、deployment transport 等做了领域专门化。它不能证明：

- 本论文 feature model 是按可复查方法从该文献“推导”出来的；
- probe generation/instrumentation 已由 prototype 实现；
- 所有 Monitoring Support 功能均已实现。

**建议用于论文的位置**：设计章 “Relationship to the General Monitoring Reference Architecture” 小节，而不是放在三个 concrete approach reconstruction 之间。它也可以作为 feature model/architecture 设计来源之一，但必须另外描述文献分析方法。

### 四张图最终如何改成论文级证据

1. **不要只保留黄色无标签箭头。** 每条映射至少标记 source role、target role、mapping rationale。
2. **建立统一图例。** 建议：绿色实线 = direct match；橙色虚线 = partial/adapter needed；红色点线 = not represented；灰色 = out of scope。
3. **区分 reference architecture 与 prototype。** 可在目标组件旁增加 `A`（architecture）与 `P`（prototype）状态，或另设一列。
4. **每图配一张映射表。** 列为 Source element、Target element、Feature configuration、Status、Evidence、Limitation。
5. **明确映射判据。** 至少检查 observation mechanism、data representation、processing、transport、property/checker、verdict/output、feedback、deployment、configuration/generation。
6. **展示负面结果。** 无法映射的部分也是评价结果，尤其是 ROSMonitoring instrumentation、ROMoSu management plane、Digital Twin state/behavior subsystem。
7. **处理图片来源。** 图注写明原论文及原 Figure 编号；最好重新绘制必要的源架构简图，仅保留评价所需元素，以改善可读性并降低图片复用风险。
8. **避免一图塞两套完整架构。** 当前四图纵向很长、箭头跨越距离大。正式论文更适合“简化源图 + 简化目标图 + 编号映射”或横向 mapping matrix。

### 这些图不能单独解决的教授意见

- **Review 85**：仍需独立的端到端用户工作流，架构映射图不能替代“用户如何获得监控基础设施”。
- **Review 94**：映射只能证明 expressiveness，不能证明节省工作量；仍需 LOC/files/steps/time 等 effort comparison。
- **Review 83**：映射不能证明五个实验是 realistic/representative。
- **Review 51、99**：这些图会出现 plugins，但不能替代 plugin interface、开发、注册和运行示例。
- **Review 44**：还需说明 feature selection + deployment configuration + generation 的实际过程。

## 整体修改意见

### 1. 首先重构论文叙事，而不是逐句打补丁

教授最核心的不满是读者无法快速回答：“这套方案是什么、用户如何得到一个监控基础设施、哪些内容由框架完成、哪些由用户完成？” 建议把全文主线固定为：

1. 从 ROS 2 运行时监控问题与现有工作缺口出发；
2. 用 feature model 描述设计空间；
3. 从 feature configuration 和额外 deployment configuration 得到具体方案；
4. 用参考架构说明稳定角色与数据流；
5. 用 generator、runtime configuration 和 plugins 实现；
6. 用 case studies、现有方法实例化、正确性、开销和工作量节省进行评价。

### 2. 明确区分四个层次

- **参考架构**：原则上支持的角色、连接、部署变化与扩展点。
- **原型实现**：本论文实际实现的 feature subset。
- **具体监控方案实例**：某次选择和配置后得到的 integrated/split deployment。
- **评价实验**：使用这些实例验证特定 criterion 的过程。

当前若混用 “architecture”“infrastructure”“runtime”“process”“deployment”“monitor”，读者会持续迷失。应建立术语表，并让图、代码名、YAML 名称和正文一致。

### 3. 重写 plugin、DSL、converter、verdict service 的故事

这是教授多次明确表示仍不理解的部分，应作为最高优先级技术重写项。需要用一个完整例子说明：

1. property 用什么 DSL/形式表达；
2. common observation record 长什么样；
3. converter 如何产生 checker-specific event；
4. verdict service 如何加载/持有 property 并检查；
5. 两类 plugin 要实现哪些接口；
6. 如何在 YAML 中注册；
7. 框架如何加载、连接并运行；
8. 最终 verdict 如何导出。

### 4. 补强数据模型与 ROS 2 观察机制

必须详细说明 common record，特别是任意 ROS 2 payload 的 primitive、array、nested type、time、byte sequence 等如何序列化及保留类型信息。另需用技术图解释 topic、service introspection 和 action feedback/status 的获取路径，并明确当前尚未覆盖的 action goal/result/cancel 或 active feedback。

### 5. 重构 Related Work

每项工作按统一标准客观描述，不要在尚未介绍自身方案时提前比较贡献。建议标准包括：

- 观察对象与观察层级；
- ROS 版本及 topics/services/actions/parameters 等覆盖；
- 观察机制与侵入性；
- 数据表示；
- property formalism 与 checker；
- online/offline；
- deployment topology；
- configuration variability；
- extension/plugin mechanism；
- 自动生成或自动组装程度。

本章结尾只总结 evidence-backed gaps；与本论文架构的映射比较移到评价或讨论。

### 6. 重新设计评价，使其直接回答 RQ

在评价章开头先定义 criteria 及来源，再建立 criterion → experiment → metric 的映射。除了功能正确性和开销，还必须加入：

- 框架节省的工作量/样板代码；
- 每个实验中 specified、generated、manually implemented、reused 的内容；
- 现有方法能否由参考架构实例化；
- case studies 为什么具有代表性/现实性；
- 明确的 pass/fail 与失败情况；
- 可复现 artifact。

### 7. 改善图表与章节可读性

- Feature model 改横向整页或拆图；
- 所有图必须在正文先引用、后解释；
- 先展示逻辑 pipeline/sequence，再展示 deployment mapping；
- UML 符号要标准，或明确声明自定义 notation；
- 数字结果放表格；
- 缩写必须展开，表头避免不透明缩写；
- 每章增加短 summary，并让下一章自然承接。

### 8. 统一 Discussion、Conclusion、Future Work

Discussion 按 RQ 组织，包含证据解释、trade-offs 和 limitations；Conclusion 重述完整 RQ 并给简短答案，不重复论证。Future Work 只保留一处，按主题列点。Threats to Validity 至少按 internal/external 分类，并加入遗漏 related work 的风险与缓解措施。

### 9. 建议的修改优先级

1. **最高优先级**：端到端用户工作流、参考架构/原型/实例层次、plugin 与 data record。
2. **高优先级**：Related Work 重构、评价标准与工作量节省、现有方法实例化。
3. **中优先级**：services/actions 技术说明、deployment/runtime/process 术语、图表重画。
4. **收尾优先级**：引用、缩写、措辞替换、章节 summary、重复内容清理、公开仓库链接。

## 完整性核对

- 独立 review 编号：1-106，连续无缺号。
- Review 原文数：106。
- 高亮批注：2 条（编号 5、6）。
- 便签批注：104 条（其余编号）。
- Popup 重复外壳：106 个，已核对但未作为独立 review 重复列出。
- Link 对象：281 个，非 review。
