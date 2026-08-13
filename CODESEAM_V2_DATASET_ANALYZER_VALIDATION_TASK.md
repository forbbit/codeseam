# CodeSeam V2 — Dataset & Analyzer Validation 任务规范

> **交付对象：Codex**
>
> **仓库：`forbbit/codeseam`**
>
> **任务性质：验证与数据基础建设，不是继续训练模型。**
>
> **本任务优先级高于继续调参、增加 epoch、追求 F1。**
>
> **核心原则：先证明“输入事实是对的、特征空间是够的、数据覆盖是足的”，再正式训练。**

---

# 0. 本轮任务一句话定义

本轮不要继续把主要精力放在：

```text
Soft-DP training
Adam
epoch
F1
cut penalty tuning
```

而要完成：

```text
Semantic Ground Truth
        ↓
可控 MATLAB 代码生成
        ↓
Static Analyzer
        ↓
Raw Facts
        ↓
与生成器已知真值逐项比较
        ↓
Analyzer Accuracy
        ↓
Raw Fingerprint
        ↓
Coverage / Counterfactual / Collision Analysis
        ↓
Feature Completeness / Identifiability
        ↓
TRAINING READINESS GATE
```

只有通过 Training Readiness Gate 后，才允许进入正式 V2 structured training。

---

# 1. 当前项目状态的正确理解

当前 V2 已经完成的内容主要属于：

```text
Architecture Prototype
```

即：

- Raw Facts 基础结构已经存在；
- Continuous Feature Model 已存在；
- Structured Energy 已存在；
- Soft-DP 已存在；
- Hard-DP 已存在；
- Structured NLL 已存在；
- Adam / autograd 链路已经可以运行；
- SemanticTaskGraph / Renderer / Fingerprint 工具已有第一版；
- Legacy V1 仍保留。

这些可以视为：

> **V2 可微训练链路 smoke test 已通过。**

但这不代表：

```text
正式训练数据已经准备好
Analyzer 已经证明准确
Fingerprint 已经覆盖充分
现有 Feature 已经证明完整
当前训练结果已经有意义
```

因此：

**当前阶段禁止把 3 epoch / 30 epoch 等训练结果当成模型能力评价。**

它们仅用于证明：

```text
forward works
loss is finite
gradient exists
optimizer updates parameters
```

---

# 2. 本轮必须暂停的事情

除非是为了验证计算图正确性，否则暂时不要继续：

- 增加 structured training epoch；
- 调 learning rate；
- 调 cut penalty；
- 调 feature weight；
- 调 module quality weight；
- 调 Soft-DP temperature；
- 为了改善当前 F1 添加新 threshold；
- 为了改善当前 F1 添加 hard prominence；
- 使用真实 GitHub MATLAB 项目直接训练；
- 用当前 V2 输出自动生成真实标签；
- 根据失败样本逐条加特殊 case；
- 根据训练结果直接删除/增加 feature。

### 允许保留的训练行为

仅允许：

```text
tiny smoke test
gradient test
finite-difference test
Soft/Hard parity test
numerical stability test
```

目的：

> 验证代码链路正确，而不是训练模型。

---

# 3. 为什么先不正式训练

当前模型训练失败或不稳定，可能由多个完全不同的问题导致：

```text
A. MATLAB Analyzer 提取事实错误
B. Analyzer 把 UNKNOWN 当成错误数值
C. Raw Facts 缺失
D. Feature 公式缺失关键语义
E. Feature 之间高度耦合
F. 数据集没有覆盖足够多的 Feature Fingerprint
G. Ground Truth 本身不独立
H. Structured Energy / 参数尺度有问题
I. Optimizer / hyperparameter 有问题
```

如果现在直接训练，无法区分这些原因。

因此必须按因果顺序排查：

```text
Analyzer correctness
        ↓
Observation completeness
        ↓
Dataset coverage
        ↓
Feature identifiability
        ↓
Energy calibration
        ↓
Formal training
```

---

# 4. 本轮总目标

本轮完成后，必须能够明确回答以下问题：

## 4.1 Analyzer 是否准确？

至少能够定量回答：

```text
Definitions 准确率？
Reads 准确率？
Mutations 准确率？
Data dependency edge 准确率？
Control dependency edge 准确率？
Call resolution 准确率？
Operation role 准确率？
Completion-related fact 准确率？
UNKNOWN 占多少？
不同 risk family 的准确率分别如何？
```

---

## 4.2 当前 Raw Facts 是否足够表达边界语义？

能够识别：

```text
相同/极近 Raw Fingerprint
但 Ground Truth 不同
```

的 collision。

如果 collision 大量存在，说明：

> 当前观测事实不够，禁止进入训练。

---

## 4.3 数据集是否覆盖足够多的 Raw Fingerprint？

必须能够回答：

```text
哪些区域覆盖充分？
哪些区域几乎没有？
哪些 feature 总是一起变化？
哪些 counterfactual 没有覆盖？
哪些四象限不完整？
```

---

## 4.4 特征是否可辨识？

必须能够回答：

```text
variable_death 与 vocabulary_shift 是否总是共线？
dependency_mass 与 completion 是否几乎同一信号？
interface_compactness 是否只在某一类样本中变化？
role_transition 是否有独立激活样本？
long-range coupling 是否真的出现过独立变化？
```

---

# 5. 正确的数据生成逻辑

## 5.1 Ground Truth 必须先于 MATLAB 源码

正确：

```text
Semantic Program
    ↓
真实 Task / Segment
    ↓
Ground Truth
    ↓
Renderer
    ↓
MATLAB
```

禁止：

```text
MATLAB
    ↓
CodeSeam feature
    ↓
根据 feature 高低决定 Ground Truth
```

---

# 6. Semantic Program 必须升级为真正的“语义真值源”

当前 `SemanticTaskGraph` 如果只是：

```text
Task A
Task B
Task C
```

还不够。

它需要保存足以验证 Static Analyzer 的语义事实。

建议对每个 Semantic Program 显式记录：

```text
task_id
segment_id
operation_role

semantic_inputs
semantic_outputs

definitions
reads
mutations

producer-consumer relationships

control structure
control parent
branch relationship
loop relationship

expected data dependency
expected control dependency

finalization relationship

long-range dependency

shared configuration
shared final output
temporary variables

expected Ground Truth cuts
```

---

# 7. Semantic Task Graph 与 Raw Fact Oracle 必须解耦

Semantic Task Graph 不应该直接保存：

```text
expected dependency_drop = 0.82
expected variable_death = 0.91
```

因为这些已经是 feature。

应该保存客观语义事实：

```text
x defined in task A
x read by statement 7
task A output consumed once by task B
loop temporary t is finalized by mean(t)
```

然后：

```text
Semantic Facts
      ↓
MATLAB Renderer
      ↓
Analyzer
      ↓
Analyzer Raw Facts
```

再比较：

```text
Expected Raw Facts
vs
Observed Raw Facts
```

---

# 8. MATLAB Renderer V2：必须支持因子化生成

当前 Renderer 如果主要只是变量命名变化，则远远不够。

必须逐步支持以下维度。

---

## 8.1 Control Structure

至少：

```text
none
if
if/else
for
while
nested if
nested loop
loop + branch
```

要求：

同一个 semantic task 在多个 control surface form 下仍保持相同 Ground Truth。

---

## 8.2 Variable Reuse

至少：

```text
low reuse
medium reuse
high reuse
complete renaming
in-place overwrite
temporary-heavy
```

---

## 8.3 Interface Width

至少：

```text
0
1
2
4
8+
```

并允许：

```text
large interface + true cut
large interface + false cut
```

---

## 8.4 Dependency Strength

至少：

```text
none
weak
medium
strong
```

---

## 8.5 Dependency Span

至少：

```text
local
medium
long
mixed
```

---

## 8.6 Operation Role

至少覆盖当前 frontend 已支持的 role：

```text
ACQUISITION
TRANSFORMATION
AGGREGATION
SHAPING
NORMALIZATION
DECISION
OUTPUT
CONTROL_COMPUTATION
UNKNOWN
```

---

## 8.7 Completion Tail

至少：

```text
0 statements
1
2
3-4
5-8
long
```

例如：

```matlab
for ...
end
mean(...)
normalize(...)
reshape(...)
```

必须允许控制：

```text
这些语句属于原任务
```

或：

```text
这些语句属于新任务
```

---

## 8.8 Module Size

至少：

```text
tiny
small
medium
large
highly imbalanced
```

---

## 8.9 Call / Effect Variation

至少：

```text
same role + different calls
different role + same broad call family
logging inside task
output at task end
output as separate task
```

---

## 8.10 Risk Variants

单独生成，不和普通 clean corpus 混淆：

```text
eval
assignin
run
dynamic load
function handle
ambiguous call/index
external unresolved call
```

Ground Truth 仍然已知，但 Analyzer 可以合法输出 UNKNOWN / low confidence。

---

# 9. Counterfactual 必须系统化

当前 counterfactual 不能只做 vocabulary。

每个核心 feature family 都必须有：

```text
正证据 + true cut
正证据 + false cut
弱证据 + true cut
弱证据 + false cut
```

也就是四象限。

---

# 10. 必须完成的 Counterfactual Families

## 10.1 Vocabulary

```text
true cut + high vocabulary shift
true cut + low vocabulary shift
false cut + high vocabulary shift
false cut + low vocabulary shift
```

---

## 10.2 Interface

```text
true cut + compact interface
true cut + wide interface
false cut + compact interface
false cut + wide interface
```

---

## 10.3 Dependency

```text
true cut + weak cross dependency
true cut + strong cross dependency
false cut + weak cross dependency
false cut + strong cross dependency
```

---

## 10.4 Role Transition

```text
true cut + strong role transition
true cut + same role
false cut + strong role transition
false cut + same role
```

---

## 10.5 Completion

```text
true cut + structurally complete
true cut + small follow-up
false cut + structurally complete-looking
false cut + long same-task finalization
```

---

## 10.6 Long-range Coupling

```text
true cut + long-range config reuse
true cut + no long-range reuse
false cut + long-range algorithm state
false cut + weak long-range dependency
```

重点：

必须区分：

```text
共享 config
```

与：

```text
同一个任务仍未结束
```

---

## 10.7 Module Size

```text
true cut creating small module
true cut creating balanced modules
false cut creating apparently balanced modules
false cut creating tiny orphan
```

---

# 11. Semantic Oracle Corpus 必须真正建立

当前只有 Oracle API 不够。

必须生成：

```text
oracle/*.json
oracle/*.m
```

或等效结构。

每一个 Oracle Case 都要同时包含：

```text
MATLAB source
Expected Definitions
Expected Reads
Expected Mutations
Expected Data Edges
Expected Control Edges
Expected Calls
Expected Roles
Expected Risks
Expected Completion Facts
```

---

# 12. Oracle Case 必须有两类

## 12.1 Hand-authored Oracle

规模不需要很大。

目标：

验证基础 MATLAB 语义。

例如：

```text
simple assignment
reuse
overwrite
if
if/else
loop
loop-carried dependency
nested control
break
continue
return
function call
aggregation
normalization
shaping
```

这些应该是：

```text
human-readable
small
deterministic
```

---

## 12.2 Generator Oracle

由 Semantic Task Graph 自动产生。

优点：

```text
规模大
Ground Truth 自动已知
可覆盖组合空间
```

但必须确保：

> Renderer 本身不能通过复用 Analyzer 逻辑来生成 Expected Facts。

否则又形成 circular validation。

---

# 13. Analyzer Accuracy Report

新增正式报告：

```text
reports/analyzer_accuracy.json
reports/analyzer_accuracy.md
```

至少按以下 family 输出。

---

## 13.1 Definitions

```text
TP
FP
FN
Precision
Recall
F1
Unknown
```

---

## 13.2 Reads

同上。

---

## 13.3 Mutations

同上。

---

## 13.4 Data Dependency Edges

必须按 edge exact match。

---

## 13.5 Control Dependency Edges

必须按 edge exact match。

---

## 13.6 Call Resolution

至少：

```text
correct resolved
wrong resolved
unknown
```

---

## 13.7 Role Classification

输出 confusion matrix。

---

## 13.8 Completion

至少比较：

```text
expected follow-up chain
observed follow-up chain

expected unfinished dependency
observed unfinished dependency
```

---

# 14. UNKNOWN 必须独立统计

报告中不能只有：

```text
accuracy = 98%
```

还必须有：

```text
known accuracy
unknown coverage
```

例如：

```text
Dependency:
known accuracy = 0.97
unknown coverage = 0.42
```

这和：

```text
Dependency:
accuracy = 0.55
unknown = 0
```

含义完全不同。

---

# 15. 当前真实项目的 low dependency confidence 必须专项诊断

当前 real-project validation 中，大量 boundary dependency confidence 较低。

本轮必须新增：

```text
dependency_confidence_diagnosis.md/json
```

至少按原因统计：

```text
parse error
unresolved call
ambiguous call/index
dynamic workspace
alias uncertainty
external dependency
global/persistent state
unknown role
other
```

要求：

```text
count
percentage
representative examples
```

不能只报告：

```text
2963 boundaries low confidence
```

必须解释为什么。

---

# 16. Raw Fingerprint 必须扩展

当前 fingerprint 如果主要是简单数值 counts，不够。

至少增加：

```text
symbol lifecycle counts

interface width

dependency count
dependency mass
dependency span mean/max/histogram

role histogram left/right

call histogram / set statistics

effect histogram / set statistics

control type

nesting depth

completion chain length
unfinished work mass

module size left/right

risk flags
reliability values
```

---

# 17. Fingerprint 必须区分连续和离散维度

不能直接：

```text
Euclidean(all raw values)
```

因为不同维度量纲差异很大。

例如：

```text
dependency_span = 100
```

与：

```text
confidence = 0.2
```

直接欧氏距离没有意义。

---

# 18. Fingerprint Normalization

至少支持：

## Continuous count-like

使用：

```text
log1p
robust scaling
quantile scaling
```

之一。

---

## Probability

保持：

```text
0..1
```

---

## Categorical

使用：

```text
one-hot
```

或 category distance。

---

## Histogram

先归一成 distribution。

---

# 19. Coverage 不只是 Novelty

必须同时统计：

```text
factor-bin coverage
pairwise coverage
three-way coverage
label balance per bin
counterfactual completeness
continuous novelty
```

---

# 20. Factor Coverage Matrix

生成类似：

```text
Interface × GroundTruth
Dependency × GroundTruth
RoleTransition × GroundTruth
Completion × GroundTruth
Control × GroundTruth
```

报告。

例如：

| Interface | True Cut | False Cut |
|---|---:|---:|
| Small | 200 | 210 |
| Medium | 190 | 205 |
| Large | 185 | 198 |

如果出现：

```text
Large + False Cut = 0
```

则该数据集不允许进入正式训练。

---

# 21. Pairwise Coverage

至少检查核心因子的 pairwise combination：

```text
Interface × Dependency
Interface × Role
Dependency × Completion
Role × Completion
Control × Dependency
Control × Completion
```

并在每个组合下进一步看 label。

---

# 22. Feature Fingerprint Collision

定义：

```text
两个样本 raw fingerprint 非常接近
但 Ground Truth 不同
```

必须自动输出：

```text
collision_report.md/json
```

---

# 23. Collision 分两类

## 23.1 Healthy Collision

例如：

```text
raw fact 很像
但有一个现有 feature 能稳定区分
```

允许。

---

## 23.2 Unexplainable Collision

```text
Raw Facts 几乎完全相同
Ground Truth 不同
```

说明：

> 现有观测空间缺失语义。

必须暂停训练并新增 Raw Fact / semantic feature。

---

# 24. Feature Independence / Identifiability

在“不训练模型”的情况下先做数据层分析。

至少输出：

```text
Pearson
Spearman
mutual information
effective rank / SVD
condition number（如适用）
```

---

# 25. 必须检查的已知相关组

## Symbol

```text
variable_death
variable_birth
vocabulary_shift
```

---

## Interface

```text
interface_compactness
input_interface_compactness
output_interface_compactness
```

---

## Dependency

```text
dependency_drop
dependency_mass
long_range_coupling
target_dispersion
```

---

## Completion

```text
structural_support
unfinished_work
completion
control_followup
```

---

# 26. 不要求统计独立

目标不是：

```text
corr ≈ 0
```

而是：

> 每一个 feature 至少有一些训练样本可以让它独立变化。

例如：

```text
dependency 改变
role 不变
completion 不变
interface 不变
```

这样的 sample 必须存在。

---

# 27. 单因素可激活性测试

对于每个核心 Feature Family：

找到至少一个 controlled sample pair：

```text
A
B
```

满足：

```text
只有目标语义因子明显变化
其他主要因子尽量不变
```

然后验证：

```text
对应 Raw Fact / Feature 确实发生预期变化
```

---

# 28. Feature Formula Unit Validation

本轮虽然不训练参数，但要验证公式方向。

例如：

## Interface

```text
interface width ↑
=> compactness evidence ↓
```

---

## Unfinished Work

```text
unfinished mass ↑
=> completion evidence ↓
```

---

## Dependency Coupling

必须明确统一方向：

如果 feature 定义为：

```text
dependency_coupling
```

则：

```text
coupling ↑
=> boundary support ↓
```

如果 feature 定义为：

```text
dependency_decoupling
```

则：

```text
decoupling ↑
=> boundary support ↑
```

不要让 feature 名称和方向混乱。

---

# 29. 特征方向统一建议

优先让所有：

```text
boundary support features
```

满足：

```text
value ↑ => more evidence to cut
```

例如：

```text
variable_death_support
variable_birth_support
interface_compactness
dependency_decoupling
role_transition_support
completion_support
local_cohesion_support
```

对于：

```text
coupling
unfinished work
orphan risk
```

更适合定义为 penalty。

不要依赖 unrestricted negative weight 来解释正反方向。

---

# 30. 当前 unrestricted weight 必须做诊断

在正式训练之前：

输出当前 parameterization。

检查：

```text
feature weight 是否可正可负？
module weight 是否可正可负？
global scale 是否自由？
cut penalty 是否自由？
energy bias 是否自由？
```

如果多个参数可以同时任意缩放而不改变 argmax，则存在 identifiability 问题。

本轮只做诊断。

不要立刻通过调参解决。

---

# 31. Semantic Dataset Manifest

每个生成样本必须有 metadata。

建议：

```json
{
  "semantic_program_id": "...",
  "renderer_seed": 123,
  "split": "train",

  "ground_truth": {
    "cuts": [5, 13],
    "tasks": [...]
  },

  "semantic_factors": {
    "interface_regime": "large",
    "dependency_regime": "long",
    "role_transition_regime": "strong",
    "completion_tail": 4,
    "control_regime": "nested",
    "variable_reuse": "high"
  }
}
```

---

# 32. Split 必须在 Semantic Graph 层完成

同一：

```text
semantic_program_id
```

所有 renderer variants 必须属于同一个 split。

禁止：

```text
same semantic program
variant 1 -> train
variant 2 -> test
```

---

# 33. Holdout Strategy

建议：

## Train

大量 factor combinations。

---

## Validation

hold out：

```text
某些 factor combinations
某些 semantic topology
```

---

## Test

hold out：

```text
未见过的 semantic graph topology
部分 control composition
部分 role composition
部分 renderer style
```

---

# 34. 真实 MATLAB 数据本轮定位

本轮真实 MATLAB 项目：

**不作为主要训练数据。**

只用于：

```text
parser stress test
risk distribution
confidence distribution
surface syntax coverage
performance benchmark
```

---

# 35. 真实数据禁止做的事情

不要：

```text
CodeSeam 自己预测切点
↓
再把预测当 Ground Truth
```

不要：

```text
README section
comment
%% section
```

直接当真实切点标签。

这些最多可以是：

```text
weak annotation
```

不能作为主 Ground Truth。

---

# 36. 以后真实数据真正使用条件

只有存在：

```text
independent human annotations
```

时，才可以用于：

```text
real validation
real test
optional fine-tuning
```

并且最好：

```text
>= 2 annotators
```

对存在争议的 cut：

```text
ambiguous
```

而不是强行 0/1。

此项不要求本轮完成。

---

# 37. 本轮需要新增的主要报告

至少生成：

```text
reports/V2_DATASET_VALIDATION_SUMMARY.md

reports/ANALYZER_ORACLE_ACCURACY.md
reports/ANALYZER_ORACLE_ACCURACY.json

reports/DEPENDENCY_CONFIDENCE_DIAGNOSIS.md

reports/FINGERPRINT_COVERAGE.md
reports/FINGERPRINT_COVERAGE.json

reports/COUNTERFACTUAL_COVERAGE.md

reports/FINGERPRINT_COLLISIONS.md

reports/FEATURE_REDUNDANCY.md

reports/TRAINING_READINESS_GATE.md
```

---

# 38. Training Readiness Gate

本轮最重要的最终产物：

```text
TRAINING_READINESS_GATE.md
```

它决定是否允许下一阶段正式训练。

---

# 39. Gate A — Static Analyzer Accuracy

至少要求：

```text
supported clean semantic subset:
definitions / reads / mutations
达到接近 exact correctness

data/control dependency:
有明确量化指标

UNKNOWN:
原因可解释
```

具体阈值不要人为伪造。

第一次运行先报告真实指标。

如果低于可接受水平：

```text
Gate FAIL
```

并列出：

```text
错误类型
影响的 Raw Facts
需要修复的 analyzer 模块
```

---

# 40. Gate B — Fingerprint Coverage

必须满足：

```text
核心因子所有主要 bin 有样本
正/负标签都覆盖
核心 pairwise combinations 无明显空洞
```

若存在大面积空 bin：

```text
Gate FAIL
```

---

# 41. Gate C — Counterfactual Completeness

至少：

```text
Vocabulary
Interface
Dependency
Role
Completion
Long-range
Control
```

全部有正反 counterfactual。

缺任何核心 family：

```text
Gate FAIL
```

---

# 42. Gate D — Feature Observability

对于每个核心 feature：

```text
至少存在 controlled sample pair
能够独立激活/抑制它
```

如果 feature 从未独立变化：

```text
Gate FAIL
```

---

# 43. Gate E — Collision Rate

如果存在大量：

```text
near-identical Raw Fingerprint
+
opposite Ground Truth
```

且无法被现有 semantic fact 解释：

```text
Gate FAIL
```

需要先补 Raw Fact / Feature。

---

# 44. Gate F — Reliability

必须能够解释：

```text
为什么一个 fact confidence 低
```

如果真实或 synthetic clean subset 中：

```text
大部分核心 dependency fact 都 low confidence
```

则：

```text
Gate FAIL
```

---

# 45. Gate G — Leakage

必须：

```text
semantic graph leakage = 0
```

否则：

```text
Gate FAIL
```

---

# 46. Gate H — Differentiable Pipeline Smoke Test

当前应该已经满足：

```text
finite loss
nonzero gradient
Soft-DP works
Hard-DP works
```

仍保留。

但它只是一个 Gate，不是模型质量证明。

---

# 47. Gate 通过后才能开始什么

只有：

```text
A-H PASS
```

才进入下一阶段：

```text
Formal Structured Training
```

之后才能讨论：

```text
epoch
optimizer
learning rate
regularization
energy calibration
final F1
```

---

# 48. Codex 本轮执行顺序

严格按以下顺序。

---

## Phase A — Freeze Training

新增明确文档：

```text
formal_training_enabled = false
```

不一定真的加代码开关，但至少在 README / task report 中写清楚：

> 当前训练只用于 smoke test。

---

## Phase B — Expand Semantic Truth Model

让 SemanticTaskGraph 保存：

```text
task truth
dependency truth
control truth
role truth
completion truth
```

---

## Phase C — Expand MATLAB Renderer

优先加入：

```text
control
interface
dependency span
completion
role
```

不要先做更多表面随机噪声。

---

## Phase D — Oracle Corpus

生成：

```text
hand-authored oracle
generator oracle
```

---

## Phase E — Analyzer Accuracy

跑 Raw Fact oracle。

输出正式 accuracy。

---

## Phase F — Diagnose Low Confidence

重点解释 dependency confidence。

---

## Phase G — Counterfactual Generator

实现七大 feature families。

---

## Phase H — Fingerprint V2

扩展并规范化 fingerprint。

---

## Phase I — Coverage Audit

输出：

```text
factor
pairwise
label balance
novelty
```

---

## Phase J — Collision / Redundancy

输出：

```text
collision
correlation
identifiability
```

---

## Phase K — Training Readiness Gate

最终明确：

```text
READY FOR TRAINING
```

或：

```text
NOT READY
```

不允许模糊描述。

---

# 49. 本轮不要为了“完成任务”强行 PASS

如果 Analyzer 有问题：

```text
写 FAIL
```

如果 fingerprint coverage 不够：

```text
写 FAIL
```

如果 collision 很多：

```text
写 FAIL
```

本轮目标不是：

```text
把 checklist 全打勾
```

而是：

> **找到真正阻止正式训练的问题。**

---

# 50. 本轮验收标准

本轮成功不等于：

```text
F1 提升
```

真正验收：

- [ ] Ground Truth 明确独立于 Feature
- [ ] Semantic Task Graph 包含 Raw Fact 真值
- [ ] MATLAB Renderer 覆盖核心结构因子
- [ ] Oracle Corpus 已真实生成
- [ ] Analyzer Accuracy 有具体数值
- [ ] UNKNOWN coverage 有具体数值
- [ ] dependency low confidence 原因明确
- [ ] Counterfactual 不再只覆盖 vocabulary
- [ ] Interface 四象限存在
- [ ] Dependency 四象限存在
- [ ] Role 四象限存在
- [ ] Completion 四象限存在
- [ ] Long-range 四象限存在
- [ ] Control variation 存在
- [ ] Raw Fingerprint 已标准化
- [ ] Fingerprint Coverage 有量化报告
- [ ] Pairwise factor coverage 有量化报告
- [ ] Counterfactual completeness 有量化报告
- [ ] Feature correlation 有量化报告
- [ ] Feature collision 有量化报告
- [ ] Semantic split leakage = 0
- [ ] Training Readiness Gate 明确 PASS / FAIL
- [ ] 在 Gate PASS 前未进行正式模型调参

---

# 51. 最终交付给用户的报告必须回答

不要只写：

```text
implemented
```

必须回答：

### 1.

当前 MATLAB Analyzer 对我们支持的 synthetic semantic subset 到底有多准？

---

### 2.

最容易分析错的是哪类 MATLAB 结构？

---

### 3.

UNKNOWN 主要来自哪里？

---

### 4.

为什么真实项目中 dependency confidence 大量偏低？

---

### 5.

当前 Raw Fingerprint 哪些区域已经覆盖？

---

### 6.

哪些区域仍为空？

---

### 7.

哪些 Feature 高度相关？

---

### 8.

哪些 Feature 可以被独立激活？

---

### 9.

有没有 Raw Fingerprint 几乎一样但 Ground Truth 相反的样本？

---

### 10.

如果有，这意味着缺少什么语义信息？

---

### 11.

当前数据是否已经具备正式训练条件？

最后必须明确写：

```text
READY FOR FORMAL TRAINING: YES / NO
```

并附原因。

---

# 52. 与上一份 V2 重构任务的关系

上一阶段完成：

```text
Differentiable Architecture
```

本阶段完成：

```text
Data + Analyzer + Feature Observability Validation
```

下一阶段才是：

```text
Formal Structured Training
```

三者不能混在一起。

正确工程路线：

```text
V2 Architecture
    ↓
Dataset & Analyzer Validation     ← 当前
    ↓
Training Readiness Gate
    ↓
Formal Structured Training
    ↓
Calibration
    ↓
Real Human-Labeled Evaluation
    ↓
Deployment
```

---

# 53. 研究逻辑

最终研究逻辑必须保持：

```text
人工提出可解释语义假设
        ↓
静态 Analyzer 提取客观事实
        ↓
数据集主动覆盖语义因子
        ↓
验证 Analyzer 准确
        ↓
验证 Feature 可观测、可辨识
        ↓
再由数据学习连续数值参数
```

而不是：

```text
代码能训练
        ↓
不断调参数
        ↓
F1 变高
        ↓
认为算法正确
```

---

# 54. 最核心的判断原则

Codex 在本轮遇到任何问题时，按以下优先级判断：

1. **先怀疑 Analyzer 是否提取正确。**
2. **再怀疑 Raw Facts 是否缺失。**
3. **再怀疑 Dataset 是否覆盖不足。**
4. **再怀疑 Feature 是否高度耦合或不可辨识。**
5. **最后才怀疑 Optimizer。**

不要反过来。

---

# 55. 最终目标

本轮完成后，CodeSeam 应当拥有一个真正可以信任的训练前基础：

\[
\boxed{
\text{Known Semantic Truth}
\rightarrow
\text{Known-correct / Quantified Analyzer}
\rightarrow
\text{Rich Raw Fingerprint Space}
\rightarrow
\text{Counterfactual Coverage}
\rightarrow
\text{Feature Observability}
}
\]

只有这条链成立，后续：

\[
\text{Soft-DP}
\rightarrow
\text{Structured Loss}
\rightarrow
\text{Adam}
\]

训练出来的参数才有科学意义和工程价值。
