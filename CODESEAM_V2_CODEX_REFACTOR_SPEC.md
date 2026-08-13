# CodeSeam V2 重构实施说明（交付 Codex 执行）

> 目标读者：负责直接修改 `forbbit/codeseam` 仓库的 Codex / 工程开发代理  
> 文档用途：作为本轮重构的唯一主设计依据，避免在“现有实现”“目标算法”“训练逻辑”“数据集生成”“验收标准”之间产生歧义。  
> 核心原则：**保留 CodeSeam 的静态程序分析和可解释性；将现有“两阶段人工调参/网格搜索 + 硬阈值选择”重构为“固定可解释特征公式 + 连续数值参数 + 结构化可微训练 + Soft-DP 训练 / Hard-DP 推理”。**

---

## 0. 先读：本次重构不是要做什么

本次重构 **不是**：

1. 不是让优化器自动发明、搜索或符号回归特征公式。
2. 不是把 CodeSeam 改造成端到端神经网络。
3. 不是要求 MATLAB 源码、AST、CFG、PDG 本身可微。
4. 不是删除现有静态分析逻辑。
5. 不是立即删除现有 Hard-DP、CLI、JSON 输出或现有测试。
6. 不是简单把现有 15 个特征扩展成更多特征然后继续网格搜索。
7. 不是根据现有特征值反推 Ground Truth。
8. 不是用“特征高就是正确切点”这种规则生成标签。
9. 不是把 `UNKNOWN` / 风险状态当成数值 0。
10. 不是在第一阶段就破坏现有 production/inference 行为。

本次重构的目标是：

> **程序分析部分继续负责产生确定性/半确定性的 Raw Facts；人工设计的连续可解释特征公式将 Raw Facts 映射为 Boundary/Segment Energy；所有数值参数统一通过结构化 Loss 训练；训练使用 Soft-DP 以支持反向传播，工程推理使用 Hard-DP 输出确定切点。**

---

# 1. 当前 CodeSeam 的核心结构（必须理解后再修改）

当前项目的主要逻辑可以概括为：

```text
MATLAB source
    ↓
Tree-sitter / MATLAB frontend
    ↓
Program IR
    ↓
CFG
    ↓
Reaching Definitions / Control Dependence
    ↓
PDG / dependency projection
    ↓
Boundary Features
    ↓
固定权重加权得到 boundary score
    ↓
threshold / prominence / local peak 等硬筛选
    ↓
Hard-DP + module quality
    ↓
最终推荐切点
```

训练/调参侧当前实际上分为两套：

```text
A. Feature-weight tuning
   Ground Truth preference
      ↓
   pairwise ranking
      ↓
   constrained deterministic grid search
      ↓
   feature weights

B. Selection tuning
   boundary score
      ↓
   threshold / prominence / radius / reward / cut penalty
      ↓
   final cuts
      ↓
   F-score / forbidden penalty
      ↓
   grid search
```

### 当前设计中本轮重点要替换的问题

1. **特征权重和最终选择参数分两阶段训练。**
2. **Boundary score 后存在较多硬筛选：threshold、prominence、局部峰值等。**
3. **一些 completion / structural 信号是 0/1 或规则型硬值。**
4. **module quality 中存在固定权重和硬判定。**
5. **最终优化目标不是一个统一、端到端的结构化数值 Loss。**
6. **训练阶段没有显式建模“所有可能切分方案”的概率或 soft 结构。**
7. **数据生成器主要按 family/template 驱动，而不是按可观测语义因子和 Raw Fingerprint coverage 驱动。**
8. **静态分析准确率和切分模型准确率没有严格拆成两个独立 benchmark。**

---

# 2. 目标架构总览

最终目标：

```text
MATLAB Source
    ↓
[离散、确定性静态程序分析层]
AST / IR / CFG / PDG / Symbol / Call / Effect / Role / Risk
    ↓
Raw Facts + Reliability
    ↓
────────────────────────────────────
从这里开始进入可训练、可微的评分路径
────────────────────────────────────
    ↓
Continuous Interpretable Feature Functions φ(r; θ_f)
    ↓
Boundary Energy B_i
    +
Segment / Module Energy Q(a,b)
    ↓
Structured Segmentation Energy E(C)
    ↓
训练：Soft-DP / LogSumExp DP
推理：Hard-DP / Max DP
    ↓
Ground Truth Segmentation C*
    ↓
Structured Loss
    ↓
Backpropagation
    ↓
Adam / 其他梯度优化器
    ↓
统一更新全部数值参数 Θ
```

参数集合统一表示为：

\[
\Theta =
\{
\theta_f,\,
w_f,\,
\theta_q,\,
w_q,\,
\lambda_{cut},\,
\tau,\,
\text{other continuous scalar parameters}
\}
\]

注意：

- **公式结构固定。**
- **只优化数值。**
- 不允许训练器修改函数表达形式。
- 不允许训练器修改 AST/CFG/PDG 的离散解析规则。
- 所有学习出来的参数必须有清晰名称、范围、默认值和可解释含义。

---

# 3. 最重要的设计原则：哪些不需要可微，哪些必须可微

## 3.1 不需要可微的部分

以下逻辑保持离散即可：

- MATLAB parsing
- AST
- IR
- CFG construction
- reaching definitions
- control dependence
- data dependence
- PDG
- symbol reads / writes / definitions
- call resolution
- role tagging
- effect tagging
- nesting structure
- risk / uncertainty detection
- legal boundary enumeration
- hard syntactic impossibility constraints

原因：

> 我们不需要对 MATLAB 源码求梯度，也不需要对 AST 节点求梯度。

例如：

```text
cross_dependency_count = 4
```

这个 `4` 可以由离散集合运算得到，但之后如果：

\[
f = \sigma(w \cdot 4 + b)
\]

则 `w`、`b` 仍然可以正常通过反向传播训练。

## 3.2 必须进入可微路径的部分

以下逻辑需要尽量连续化：

- feature transforms
- feature combination weights
- boundary score / boundary energy
- local peak/prominence 信息（如果保留）
- completion strength
- module quality
- cut penalty
- segment energy
- soft segmentation aggregation
- final training objective

---

# 4. Raw Fact Schema：先稳定输入，再训练模型

必须新增或明确一个稳定的 **Raw Fact Schema**。

Raw Fact 是程序分析层输出的客观事实，不是经过人工归一化之后的 feature score。

建议定义一个明确的数据结构，例如：

```python
@dataclass(frozen=True)
class BoundaryRawFacts:
    boundary_index: int

    # symbol lifecycle
    left_symbol_count: int
    right_symbol_count: int
    dead_symbol_count: int
    born_symbol_count: int
    cross_symbol_count: int

    # interface
    input_interface_count: int
    output_interface_count: int

    # dependency
    cross_data_edge_count: int
    cross_control_edge_count: int
    left_internal_data_edge_count: int
    right_internal_data_edge_count: int
    left_internal_control_edge_count: int
    right_internal_control_edge_count: int

    dependency_span_mean: float
    dependency_span_max: float
    dependency_target_count: int
    dependency_reuse_mass: float

    # calls / effects / roles
    left_call_histogram: ...
    right_call_histogram: ...
    left_effect_histogram: ...
    right_effect_histogram: ...
    left_role_histogram: ...
    right_role_histogram: ...

    # structure / completion
    nesting_depth_left: int
    nesting_depth_right: int
    compound_ends_here: bool
    followup_dependency_mass: float
    completion_chain_length: int

    # module geometry
    left_context_size: int
    right_context_size: int

    # reliability
    parse_confidence: float
    call_resolution_confidence: float
    dependency_confidence: float
    dynamic_workspace_risk: float
    alias_uncertainty: float
```

以上字段名称可根据现有结构调整，但设计目标必须满足：

1. Raw Fact 与 Feature 分层。
2. Raw Fact 尽量保存“原始事实”，而不是提前压成 0~1。
3. 允许未来 feature 公式改变，而不需要重新改 parser。
4. 所有训练样本可导出 raw fingerprint。
5. 所有 raw fact 都应能追溯到静态分析来源。

---

# 5. Reliability / UNKNOWN 必须显式表示

这是本次重构必须新增的概念。

MATLAB 静态分析并非对任意语法/运行时语义都完全准确。

例如：

- `eval`
- `assignin`
- 动态 `load`
- 函数句柄
- path precedence
- 动态 dispatch
- 不可确定 alias
- 未完整支持的语句类型

不允许把“不知道”直接编码成：

```text
0 dependencies
0 calls
0 effects
```

因为这会让模型误以为“确实不存在”。

应区分：

```text
value = 0, confidence = 1.0
```

与：

```text
value = unknown/estimated, confidence = 0.2
```

推荐方案：

```python
RawValue(
    value=...,
    confidence=...
)
```

或为每一组 Raw Fact 提供 reliability mask。

### Reliability 的作用

Reliability 不应简单表示“这里是否适合切”。

它表示：

> “我们对当前 feature 输入的可信程度。”

可以考虑：

\[
\tilde f_k = m_k f_k + (1-m_k)b_k
\]

或：

\[
B_i = \sum_k w_k m_{ik} f_{ik}
\]

具体形式可在实现时设计，但必须：

- 可微；
- 可解释；
- 不把低 confidence 等同于负证据。

---

# 6. 静态分析本身必须建立独立准确率 Benchmark

切分准确率不能用于替代 frontend/IR/CFG/PDG 准确率。

新增：

```text
Semantic Oracle Corpus
```

目的：

> 只验证 MATLAB → Raw Facts 是否正确，不训练切点。

至少应验证：

- definitions
- reads
- mutations
- data-dependency edges
- control-dependency edges
- reaching definitions
- loop back edges
- branch merge
- call resolution
- operation role
- effect tagging
- completion-relevant dependencies
- risk/unknown tagging

建议分别计算：

```text
Precision / Recall / F1
```

或 exact-match / edge accuracy。

必须支持：

```text
CORRECT
WRONG
UNKNOWN
```

并在报告中单独统计 UNKNOWN coverage。

---

# 7. 特征体系 V2：不是简单增加特征，而是重构成可解释特征族

现有约 15 个 boundary features 不要求彼此统计独立。

但必须关注：

- 冗余
- 参数不可辨识
- 信息重叠
- ablation 后是否仍有独立贡献

## 7.1 Symbol Lifecycle

保留：

- variable_death
- variable_birth
- vocabulary_shift

建议改成连续函数：

\[
f_{death}
=
1-\exp(-\alpha_d \cdot dead\_ratio)
\]

\[
f_{birth}
=
1-\exp(-\alpha_b \cdot born\_ratio)
\]

或其他固定、单调、可解释函数。

要求：

- 公式固定；
- \(\alpha_d,\alpha_b\) 可训练；
- 数值范围稳定；
- 防止分母为 0。

### 必须有反例

- 大量变量死亡但任务未结束；
- 大量变量新生但仍是同一任务；
- 真实切点但变量名高度复用；
- 非切点但变量名全部变化。

---

# 8. Interface 特征

保留：

- interface_compactness
- input_interface_compactness
- output_interface_compactness

建议不要硬阈值。

例如：

\[
f_{interface}
=
\exp(-\alpha \cdot interface\_width)
\]

或归一化后：

\[
f =
\frac{1}{1 + \alpha x}
\]

可训练：

- \(\alpha\)
- relative scaling

必须构造 4 象限样本：

```text
true cut  + small interface
true cut  + large interface
false cut + small interface
false cut + large interface
```

否则模型会错误学习：

```text
small interface => cut
```

---

# 9. Dependency 特征 V2

保留现有：

- dependency_drop
- medium_dependency_drop
- dependency_target_dispersion
- local_cohesion_support

但需要增加：

## 9.1 Continuous Multi-scale Dependency

不要仅使用固定 window=4 / window=12。

设计距离权重：

\[
w(d;\tau)=\exp(-d/\tau)
\]

定义：

\[
M_i(\tau)
=
\sum_{e \in E_i^{cross}} w(d_e;\tau)
\]

其中 \(\tau\) 为可训练连续参数。

这样可以替代离散 radius / fixed window 的一部分作用。

## 9.2 Dependency Mass

不仅统计 edge 数量，还要统计：

> 一个跨边界中间结果在后续被持续使用了多少。

建议：

\[
dependency\_mass
=
\sum_{e \in cross}
g(distance_e)
\cdot
reuse(e)
\cdot
type\_weight(e)
\]

需要区分：

```text
A. 左任务输出最终结果，右任务只读取一次
B. 左任务产生中间状态，右侧 20 个语句持续依赖
```

两者 `cross_symbol_count` 可能相同，但语义不同。

---

# 10. Operation Role Transition：本轮重点新增

MATLAB frontend 已经具有 operation role 的概念，应正式进入 boundary feature。

建议至少包含：

```text
ACQUISITION
TRANSFORMATION
AGGREGATION
SHAPING
NORMALIZATION
DECISION
OUTPUT
OTHER
```

具体枚举以现有代码为准，不要自行破坏当前 role taxonomy。

定义左右窗口 role distribution：

\[
P_L^{role}, P_R^{role}
\]

可使用：

- cosine distance
- Jensen-Shannon distance
- 1 - overlap
- 可训练 transition matrix

推荐优先使用简单、可解释、稳定方案。

例如：

\[
f_{role}
=
1-\frac{P_L \cdot P_R}
{\|P_L\|\|P_R\|+\epsilon}
\]

也可加入可训练 role transition matrix：

\[
f_{role}
=
P_L^T W_{role} P_R
\]

若使用矩阵，必须：

- 对矩阵加合理约束；
- 保留可解释性；
- 不允许无限自由度。

### 必须构造 counterfactual

- role 明显变化但不是切点；
- role 不变化但是真切点；
- call set 明显变化但 role 不变化；
- call set 相似但 role 明显变化。

---

# 11. Completion / Structural Feature 必须重点重构

这是本轮最重要的 feature 重构之一。

当前类似：

```text
task_completion ∈ {0,1}
```

以及 structural completion 依赖 hard completion signal 的方式不适合结构化可微训练。

目标改为：

```text
continuous unfinished-work mass
```

## 11.1 定义 Unfinished Work

在 boundary \(i\) 之后，仍属于左侧任务的依赖越多，则 completion 越低。

可设计：

\[
U_i
=
\sum_{e \in followup(i)}
a_{role(e)}
\exp(-d_e/\tau_c)
\cdot strength(e)
\]

然后：

\[
f_{completion}
=
\exp(-\alpha_c U_i)
\]

或：

\[
f_{completion}
=
\sigma(\beta_c-\alpha_c U_i)
\]

其中：

- \(\alpha_c\) 可训练；
- \(\beta_c\) 可训练；
- \(\tau_c\) 可训练。

要求：

- 公式固定；
- completion 不再是简单 0/1；
- 不再只依赖“是否出现 end”。

## 11.2 Structural End 只作为原始证据

`for/end`、`if/end`、compound close 不应直接强行产生高 boundary score。

它应该是 Raw Fact：

```text
compound_ends_here = True
```

然后结合：

```text
unfinished_work_mass
control_followup
dependency continuation
role continuation
```

计算连续完成度。

### 必须构造样本

```text
for ... end
new independent task
```

真实应切。

以及：

```text
for ... end
mean(...)
normalize(...)
reshape(...)
```

真实不应立即切。

并覆盖 follow-up 长度：

```text
0 / 1 / 2 / 4 / 8 / long
```

不要继续只使用固定“最多 4 条”作为模型的最终语义定义。

---

# 12. Long-range Coupling：新增

增加一个区别于 local dependency 的长期耦合信号。

目标区分：

```text
global config 在很远位置再次被轻度读取
```

与：

```text
同一任务的核心中间状态跨越大量语句持续使用
```

建议 raw facts 记录：

- dependency span distribution
- mean span
- max span
- reuse frequency
- source/target role
- edge type

feature 再通过固定函数组合。

---

# 13. Call / Effect Features

保留：

- call_set_change
- effect_set_change

但注意：

- call name 改变不等于 task change；
- `fft`、`filter`、`detrend` 可能调用不同但都属于 transformation；
- logging/output 可能插在任务中间。

因此：

```text
call/effect change = 辅助证据
role transition = 更高层语义证据
```

不要让 call-set feature 主导最终模型。

---

# 14. Feature Independence / Redundancy 的处理

不要凭直觉删特征。

训练数据达到一定规模后，需要新增 feature diagnostics：

1. Pearson correlation
2. Spearman correlation
3. mutual information
4. feature ablation
5. effective rank / SVD
6. parameter sensitivity
7. gradient magnitude
8. validation drop after removing feature family

例如：

```text
corr(feature_A, feature_B) > 0.98
```

且删除 B 后：

```text
validation metric 无明显下降
```

则考虑删除 B。

注意：

> 高相关 ≠ 必须删除。

如果 adversarial cases 依赖其独立作用，则仍应保留。

---

# 15. Boundary Energy

将现有单纯加权 score 重构为明确的 energy/logit。

建议：

\[
B_i
=
b_0
+
\sum_k w_k \phi_k(r_i;\theta_k)
\]

其中：

- \(\phi_k\)：人工固定公式；
- \(\theta_k\)：公式中的连续数值参数；
- \(w_k\)：feature family weight；
- \(b_0\)：可选 bias。

不必强制先 sigmoid。

因为 structured energy 中使用 logit/energy 往往更自然。

若需要用户可解释概率，可在输出层额外提供：

\[
p_i = \sigma(B_i)
\]

但 structured DP 内部建议直接使用 energy。

---

# 16. Prominence / Local Peak：不要再作为硬筛选

当前类似：

```text
score below threshold -> drop
not local peak -> drop
prominence below threshold -> drop
```

训练阶段应移除这种不可逆 hard filtering。

## 推荐做法 A：直接删除 prominence 硬筛

把所有合法 boundary 交给 structured selector。

这是优先方案。

## 推荐做法 B：保留 prominence 作为连续 feature

例如：

\[
P_i
=
B_i
-
\sum_{j\in N(i)}a_{ij}B_j
\]

其中：

\[
a_{ij}
=
\frac{\exp(-|i-j|/\tau_p)}
{\sum_{k\in N(i)}\exp(-|i-k|/\tau_p)}
\]

\(\tau_p\) 可训练。

这样：

```text
prominence
```

只是连续证据，不再决定“能不能进入 DP”。

---

# 17. Threshold：训练阶段取消

训练阶段不要再使用：

```text
if score < threshold:
    discard
```

原因：

- 信息不可逆丢失；
- 产生非连续行为；
- 与 cut penalty 作用部分重叠；
- 不利于端到端训练。

最终推理如确有 UI/工程需要，可以提供显示阈值，但：

> **不能让它决定 Hard-DP 的候选集合，除非属于绝对安全/语法硬约束。**

---

# 18. Module Quality V2：连续化并参与统一训练

当前 module quality 的概念必须保留，因为：

> Boundary score 回答“这个位置像不像边界”；  
> Module quality 回答“切出来的这一段像不像完整模块”。

目标：

\[
Q(a,b;\theta_q)
=
\sum_m v_m q_m(a,b;\beta_m)
\]

保留现有思路，例如：

- internal cohesion
- external compactness
- symbol locality
- size fitness
- finalization completeness
- orphan resistance

但：

- 权重 \(v_m\) 可训练；
- shape 参数 \(\beta_m\) 可训练；
- hard special-case 尽量 soft 化。

例如 orphan resistance：

原：

```text
single terminal statement => 0
else => 1
```

改：

\[
q_{orphan}
=
\sigma\left(\frac{length-n_0}{T}\right)
\cdot
(1-\text{terminal-only-strength})
\]

具体公式可调整，但要求连续、单调、可解释。

---

# 19. Structured Segmentation Energy

对于切分集合：

\[
C=\{c_1,c_2,\dots,c_K\}
\]

定义：

\[
E(C)
=
\sum_{i\in C} B_i
+
\sum_{M\in Seg(C)} Q(M)
-
\lambda_{cut}|C|
-
P_{hard}(C)
\]

其中：

- \(B_i\)：boundary energy；
- \(Q(M)\)：module/segment energy；
- \(\lambda_{cut}\)：连续可训练 cut penalty；
- \(P_{hard}(C)\)：仅用于真正不允许的结构。

### Hard constraint 与 soft penalty 必须分清

Hard constraint 只用于：

- 语法上不能切；
- region 外；
- 明确违反 parser/IR invariant；
- 明确不可能作为顶层合法边界。

以下不要做 hard constraint：

- score 低；
- module 小；
- prominence 小；
- interface 大；
- dependency 高；
- task completion 不明显。

这些都应该成为 soft energy。

---

# 20. 训练使用 Soft-DP

Hard-DP：

\[
V(j)
=
\max_{i<j}
[
V(i)+R(i,j)
]
\]

训练时替换为：

\[
V(j)
=
T\log
\sum_{i<j}
\exp\left(
\frac{V(i)+R(i,j)}{T}
\right)
\]

即 LogSumExp / Soft-DP。

其中：

- \(T\)：temperature；
- 可固定，也可训练，但建议第一版固定；
- 数值实现必须使用稳定 logsumexp；
- 不允许直接 `exp()` 后求和导致 overflow。

### Soft-DP 的目的

训练阶段计算所有合法 segmentation 的 partition function：

\[
Z(X)
=
\sum_C \exp(E(C))
\]

或：

\[
\log Z(X)
=
\operatorname{LogSumExp}_C E(C)
\]

不需要显式枚举指数级 segmentation，必须使用动态规划。

---

# 21. Structured Loss：优先采用真实分割集合直接监督

本轮不建议首先人为定义每个 boundary 的连续 Ground Truth `y_i`。

数据集只需要提供真实 segmentation：

\[
C^*
\]

结构化条件概率：

\[
P(C|X)
=
\frac{\exp(E(C))}
{Z(X)}
\]

Loss：

\[
L_{struct}
=
-\log P(C^*|X)
\]

即：

\[
L_{struct}
=
-E(C^*)+\log Z(X)
\]

这是首选主 Loss。

### 为什么优先不用手工 `y_i`

因为真实任务是：

> 对整个程序选择一组彼此关联的切点。

并不是：

> 每个位置独立二分类。

因此结构化监督更加自然。

---

# 22. 可选 Auxiliary Loss

如需要更稳定训练，可以增加辅助 loss，但不得替代 Structured Loss。

例如：

## 22.1 Boundary Auxiliary Loss

从 Soft-DP 推导或直接使用 boundary marginal：

\[
p_i=P(i\in C|X)
\]

对真实边界做 BCE / soft BCE。

## 22.2 Forbidden Penalty

明确 forbidden 的边界：

\[
L_{forbidden}
=
\sum_{i\in forbidden} p_i
\]

注意：

- forbidden 如果是真正语法非法，应直接 Hard constraint；
- 如果只是人工“不推荐”，应为 soft penalty。

总 Loss 可写：

\[
L
=
L_{struct}
+
\lambda_bL_{boundary}
+
\lambda_fL_{forbidden}
+
\lambda_rL_{regularization}
\]

第一版建议尽量简单：

```text
Structured NLL + small regularization
```

---

# 23. 推理使用 Hard-DP

训练：

```text
Soft-DP / LogSumExp
```

工程推理：

```text
Hard-DP / max
```

即：

\[
C_{hard}
=
\arg\max_C E(C)
\]

必须保证：

- Soft-DP 与 Hard-DP 使用同一组 energy 函数；
- 使用同一组训练参数；
- 不出现训练一套规则、推理另一套规则；
- inference deterministic；
- 保持 CLI / JSON 输出兼容或提供版本化输出。

---

# 24. 数据集设计：Ground Truth 必须在语义层确定

禁止：

```text
先生成 MATLAB
→ 计算 feature
→ feature 高
→ 标为真实切点
```

这属于 circular supervision。

正确流程：

```text
Semantic Task Graph
    ↓
真实任务分段已经确定
    ↓
Ground Truth cuts
    ↓
MATLAB Renderer
    ↓
MATLAB source
    ↓
CodeSeam Analyzer
    ↓
Raw Facts / Features
```

也就是说：

> Ground Truth 必须独立于 CodeSeam 特征公式存在。

---

# 25. 新增 Semantic Task Graph

建议新增一个内部生成 DSL / Python object，不要求用户看到。

例如：

```python
Task(
    role="ACQUISITION",
    inputs=[],
    outputs=["raw"],
    internal_steps=4,
)

Task(
    role="TRANSFORMATION",
    inputs=["raw"],
    outputs=["clean"],
    internal_steps=6,
)

Task(
    role="AGGREGATION",
    inputs=["clean"],
    outputs=["feature"],
    internal_steps=3,
)
```

真实切点天然位于：

```text
Task A | Task B | Task C
```

Semantic Task Graph 应支持：

- sequential tasks
- nested tasks
- shared input
- shared config
- intermediate outputs
- final outputs
- control flow
- loops
- branch
- post-processing tail
- optional output/logging
- data reuse
- long-range dependency

---

# 26. MATLAB Renderer：同一语义生成多种表面形式

Renderer 应把一个 semantic graph 随机/因子化渲染为多种 MATLAB surface form。

可变化：

- variable naming
- variable reuse
- temp variable insertion
- vectorized vs loop
- helper function vs inline
- if vs logical indexing
- local post-processing
- extra logging
- comments
- whitespace
- call synonyms（在不改变语义前提下）
- reshape/transpose variations
- loop finalization position
- output timing
- irrelevant local temporary values

目标：

> 同一 Ground Truth segmentation 对应多个不同 Raw Fingerprint。

---

# 27. Counterfactual 数据必须成为一等公民

不要只生成“自然样本”。

必须生成专门打破特征相关性的 counterfactual pairs。

## Vocabulary

```text
A: true cut + variable names change
B: true cut + variable names reused
C: false cut + variable names change
D: false cut + variable names reused
```

## Interface

```text
true cut + small interface
true cut + large interface
false cut + small interface
false cut + large interface
```

## Structural End

```text
loop end + new task
loop end + same task finalization
```

## Role Transition

```text
role changes + true cut
role changes + false cut
same role + true cut
same role + false cut
```

## Dependency

```text
low dependency + true cut
low dependency + false cut
high dependency + true cut
high dependency + false cut
```

如果没有这些样本，模型会把相关性错误当成因果规律。

---

# 28. Raw Feature Fingerprint

每个 candidate boundary 必须可以导出 raw fingerprint：

\[
r_i=[r_{i1},...,r_{ip}]
\]

用于：

- coverage
- novelty
- collision detection
- missing-feature detection
- dataset balancing

至少包括：

- symbol counts
- interface counts
- dependency counts
- dependency spans
- role distributions
- call/effect distributions
- nesting
- completion tail
- module lengths
- risk/confidence
- control type
- reuse statistics

---

# 29. 数据集生成目标：覆盖 Feature Space，不是堆程序数量

数据生成器必须增加 factorized generation。

示例因子：

```text
control:
  none / if / if-else / for / while / nested

role transition:
  same / weak / strong

interface:
  tiny / small / medium / large

dependency:
  low-local / high-local / low-long / high-long

symbol reuse:
  low / medium / high

completion tail:
  0 / 1 / 2-4 / 5-8 / long

module size:
  tiny / small / medium / large

module balance:
  balanced / left-heavy / right-heavy

risk:
  clean / unresolved-call / dynamic-workspace
```

要求：

- 重要因子至少 pairwise coverage；
- 核心因子尽量 three-way coverage；
- 正负 Ground Truth 都要覆盖相同/相近因子组合。

---

# 30. Fingerprint Coverage Sampler

生成候选样本后，不要全部保留。

计算标准化 fingerprint：

\[
z_i
\]

定义 novelty：

\[
Novelty(z_i)
=
\min_{z_j\in D}
d(z_i,z_j)
\]

保留新颖样本。

但不能仅按 novelty，因为极端 outlier 会占满数据集。

建议 sample value：

\[
S
=
\alpha Novelty
+
\beta CoverageDeficit
+
\gamma CounterfactualValue
+
\delta Hardness
\]

其中：

- Novelty：离已有样本多远；
- CoverageDeficit：当前某一组合 bin 是否不足；
- CounterfactualValue：是否补齐正/负对；
- Hardness：当前模型是否容易判断错。

---

# 31. Active Dataset Generation（后续阶段）

第一版训练完成后允许：

```text
train model
    ↓
find high-loss fingerprint regions
    ↓
request generator to create targeted samples
    ↓
retrain
```

例如发现：

```text
large interface + true cut
```

recall 很低，则定向生成更多这种组合，并变化其他因素。

这属于后续阶段，不要求第一 PR 全部实现，但架构要允许接入。

---

# 32. Missing Feature Detection

这是必须加入诊断工具的思想。

寻找：

\[
d(r_i,r_j) < \epsilon
\]

但：

\[
label_i \ne label_j
\]

也就是：

> 当前 Raw Fingerprint 几乎一样，但 Ground Truth 不一样。

这说明：

- 不是优化器参数的问题；
- 很可能是 Raw Fact / Feature 集合缺少关键信息。

需要输出这类 collision pair 给开发者检查。

新增诊断报告：

```text
fingerprint collisions with contradictory labels
```

优先级高于无脑继续调权重。

---

# 33. 数据集分层

至少分四层：

## A. Semantic Oracle Corpus

用途：

- 测 frontend / IR / CFG / PDG 正确性
- 不训练 cut model

## B. Controlled Synthetic Corpus

用途：

- 主训练集
- factorized coverage
- Ground Truth 完全已知

## C. Adversarial / Counterfactual Corpus

用途：

- 打破 feature shortcut
- 检测过拟合规则

## D. Real MATLAB Corpus

用途：

- validation
- test
- calibration
- 后期 fine-tune（如需要）

不要让真实 GitHub 项目成为第一阶段唯一训练来源。

---

# 34. Train / Validation / Test 划分原则

禁止只随机按文件切。

必须防止 semantic leakage。

建议：

## Train

- semantic graph families A/B/C
- multiple render variants

## Validation

- unseen semantic graph topology
- unseen factor combinations

## Test

- unseen task composition
- unseen nesting structure
- unseen renderer style
- real MATLAB projects

目标：

> 测 generalization，不是测模板记忆。

---

# 35. 训练参数与配置

新增统一 config，例如：

```yaml
model:
  feature_version: boundary-features-v2-structured

  feature_parameters:
    death_alpha: ...
    birth_alpha: ...
    interface_alpha: ...
    dependency_tau: ...
    completion_tau: ...
    completion_alpha: ...
    role_weight: ...

  feature_weights:
    variable_death: ...
    variable_birth: ...
    ...
    role_transition: ...

  module_quality:
    cohesion_weight: ...
    compactness_weight: ...
    locality_weight: ...
    size_weight: ...
    finalization_weight: ...
    orphan_weight: ...

  segmentation:
    cut_penalty: ...
    soft_dp_temperature: ...

training:
  optimizer: adam
  learning_rate: ...
  weight_decay: ...
  epochs: ...
  gradient_clip: ...
```

要求：

- 参数统一存储；
- 不再分 “feature weights file” 与 “selection tuning file” 两套独立训练产物；
- 可以保留 legacy config 兼容读取；
- 新模型必须有 version/schema version。

---

# 36. 参数约束

很多参数需要保持正值或范围限制。

不要在每个 forward 手动 clamp 导致梯度不稳定。

推荐 reparameterization：

```text
positive:
  x = softplus(raw_x)

0..1:
  x = sigmoid(raw_x)

simplex weights:
  w = softmax(raw_w)
```

Feature weights 是否必须归一到 1，需要根据 energy 定义决定。

如果不需要，不要强制归一。

但必须避免：

```text
feature weights 与 cut penalty 同时无界缩放
```

导致 identifiability 问题。

可使用：

- weight normalization
- L2 regularization
- fixed global energy scale
- temperature fixing

第一版建议：

> 固定 Soft-DP temperature，控制 feature weight 范数。

---

# 37. 数值稳定性

Soft-DP 必须：

- 使用 stable `logsumexp`
- 避免 `exp(large_number)`
- 支持长脚本
- 支持 batch 中不同长度
- 无 NaN / Inf
- 对极短脚本定义明确

需要测试：

```text
1 boundary
10 boundaries
100 boundaries
1000 boundaries
```

至少确保合理脚本长度可稳定训练。

---

# 38. PyTorch / Autograd 实现建议

如果当前项目不是 PyTorch，可新增训练专用依赖层。

推荐：

```text
static analyzer:
  existing Python objects / NumPy

        ↓ convert

torch.Tensor raw features
        ↓
differentiable feature functions
        ↓
energy
        ↓
Soft-DP
        ↓
loss
```

不要把 parser / CFG 全部改写成 Torch。

边界：

```text
StaticAnalyzer = non-differentiable
StructuredScorer = differentiable
```

必须保持模块职责清晰。

---

# 39. 建议新增/重构文件

具体路径需以仓库当前结构为准，可适当调整。

建议：

```text
src/codeseam/core/raw_facts.py
    Raw Fact Schema

src/codeseam/core/feature_model.py
    连续特征函数

src/codeseam/core/structured_energy.py
    Boundary + Segment energy

src/codeseam/core/soft_dp.py
    differentiable partition / marginals

src/codeseam/core/hard_dp.py
    production argmax DP
    或保留现有 scoring.py 中 Hard-DP

src/codeseam/training/structured_loss.py
    structured NLL

src/codeseam/training/trainer.py
    unified optimizer

src/codeseam/training/config.py
    parameter schema

src/codeseam/corpus/semantic_graph.py
    latent task representation

src/codeseam/corpus/matlab_renderer.py
    semantic -> MATLAB

src/codeseam/corpus/fingerprint.py
    raw fingerprint

src/codeseam/corpus/coverage.py
    coverage / novelty / collision

src/codeseam/evaluation/semantic_oracle.py
    frontend correctness benchmark
```

现有：

```text
features.py
scoring.py
module_quality.py
completion.py
training.py
selection_tuning.py
generator.py
```

不要第一步直接删除。

先：

1. 抽取共享逻辑；
2. 新旧路径并行；
3. 增加 version switch；
4. 完成回归；
5. 再标 legacy/deprecated。

---

# 40. Legacy 与 V2 的关键差异

| 项目 | 当前 | V2 |
|---|---|---|
| 特征公式 | 固定 | 固定 |
| 优化对象 | 主要 feature weights | 所有连续数值参数 |
| Feature tuning | ranking grid search | gradient-based unified training |
| Selection tuning | separate grid search | integrated into same loss |
| threshold | hard | training 中取消 |
| prominence | hard candidate filter | 删除或连续化 feature |
| task completion | 偏硬/0-1 | continuous unfinished-work |
| module quality | fixed weights + hard rules | continuous + trainable |
| candidate filtering | 多级硬筛 | 所有合法候选交给 structured selector |
| training selector | Hard-DP | Soft-DP |
| inference selector | Hard-DP | Hard-DP |
| loss | ranking + selection metric | structured NLL |
| Ground Truth | preferred/discouraged/forbidden | true segmentation + optional soft annotations |
| dataset | family templates | semantic graph + factorized renderer + fingerprint coverage |
| uncertainty | risk mostly outside feature | explicit reliability/confidence |
| frontend evaluation | 与系统测试耦合 | 独立 semantic oracle benchmark |

---

# 41. 迁移顺序（必须按阶段执行）

## Phase 0 — Baseline Freeze

先做：

- 跑完整现有测试；
- 保存 baseline metrics；
- 保存若干典型 MATLAB 输入及当前输出；
- 保存当前 weights/config；
- 确认 CLI 与 JSON schema。

产物：

```text
baseline_report.md / json
```

---

## Phase 1 — Raw Facts Extraction

目标：

- 将 `features.py` 中可复用的原始统计抽成 Raw Fact；
- 不改变当前 V1 输出；
- V1 feature 仍从 Raw Fact 重建并与旧结果 bitwise/approximately equivalent。

验收：

```text
旧 features.py 结果
≈
RawFacts -> legacy_feature_adapter 结果
```

这是最关键的安全迁移点。

---

## Phase 2 — Semantic Oracle Benchmark

目标：

- 为静态分析单独建 corpus；
- 增加 definitions/reads/dependencies/control edges 等准确率测试；
- 引入 UNKNOWN/confidence。

验收：

- 每类 Raw Fact 有明确 accuracy 报告；
- unsupported behavior 不再被静默当成 0。

---

## Phase 3 — Continuous Feature Model

目标：

- 实现 V2 continuous feature transforms；
- 先不接 Soft-DP；
- 对每个 boundary 输出 feature decomposition。

必须可解释输出：

```json
{
  "boundary": 42,
  "features": {
    "variable_death": 0.71,
    "role_transition": 0.83,
    "completion": 0.24
  },
  "weighted_contributions": {
    ...
  },
  "boundary_energy": 1.37
}
```

---

## Phase 4 — Continuous Module Quality

目标：

- 将 module quality 从固定/硬规则改成可微 score；
- 保留 legacy module quality 做对照；
- segment energy API 固定。

---

## Phase 5 — Soft-DP

目标：

实现：

- log partition
- structured NLL
- optional boundary marginals
- numerical stability tests

同时验证：

当 temperature → 很小：

```text
Soft-DP best path
≈
Hard-DP best path
```

不要求完全相等，但应趋势一致。

---

## Phase 6 — Unified Training

目标：

- Adam 优化；
- feature 参数、feature 权重、module 参数、cut penalty 同时训练；
- 不再依赖 legacy grid search 作为主训练。

保留 legacy training 命令，暂时标记：

```text
legacy
```

不要直接删除。

---

## Phase 7 — Semantic Dataset Generator V2

实现：

- Semantic Task Graph
- MATLAB Renderer
- factor grid
- counterfactual pairs
- fingerprint extraction
- coverage sampler

旧 17-family generator 可以作为：

```text
legacy templates / seed semantic templates
```

继续使用。

---

## Phase 8 — Real Corpus Validation

最后才做：

- real MATLAB validation
- error taxonomy
- calibration
- missing feature analysis

如果 synthetic 好、real 差：

不要第一反应继续加参数。

优先检查：

1. frontend accuracy
2. fingerprint coverage gap
3. missing semantic fact
4. renderer distribution mismatch

---

# 42. 测试要求

至少新增以下测试。

## Static Analysis

- reads
- definitions
- mutations
- data edges
- control edges
- loops
- branches
- nested control
- unresolved calls
- dynamic workspace
- confidence propagation

## Feature Functions

- monotonicity
- output range
- zero denominator
- extreme values
- gradients finite
- parameter gradients nonzero where expected

## Soft-DP

- tiny hand-computable cases
- one possible cut
- no cut
- multiple cuts
- hard constraints
- partition correctness
- gradient check
- numerical stability

## Hard-DP

- deterministic
- matches legacy behavior where expected
- respects syntax hard constraints

## Dataset

- Ground Truth defined before rendering
- no label derivation from features
- no semantic graph leakage across split
- counterfactual pair generation
- fingerprint coverage
- collision report

---

# 43. Gradient Check

对 Soft-DP 与核心 feature 参数必须做：

- autograd
- finite differences

比较：

\[
\frac{\partial L}{\partial \theta}
\]

不能只检查 loss 能下降。

至少在小样本上验证梯度方向正确。

---

# 44. Ablation

V2 完成后必须重新做 family-level ablation。

至少：

```text
remove symbol family
remove dependency family
remove interface family
remove role family
remove completion family
remove module quality
remove reliability
```

目的：

- 验证新增 feature 真正有用；
- 找出冗余；
- 防止参数数量增加但泛化不提升。

---

# 45. 诊断输出

训练报告必须包含：

- train structured NLL
- validation structured NLL
- hard inference precision / recall / F1
- exact segmentation accuracy
- distance-tolerant cut metric（可选）
- average cut count error
- forbidden rate
- feature contribution statistics
- feature correlation matrix
- parameter values
- gradient magnitudes
- Raw Fact confidence distribution
- fingerprint coverage
- fingerprint collision count

---

# 46. 成功标准

本轮不是以“某一个 F1 必须达到 X”作为唯一成功标准。

第一阶段更重要的是架构正确。

最低验收标准：

1. V1 路径仍可运行。
2. Raw Facts 与 feature 分离。
3. uncertainty/confidence 能显式表达。
4. V2 feature model 连续、可微。
5. module quality 连续、可微。
6. Soft-DP 可稳定求 partition 和 loss。
7. Hard-DP 使用与训练相同的 energy。
8. Structured Loss 可反向传播到所有目标数值参数。
9. Ground Truth 不由 feature 反推。
10. Synthetic generator 能生成 counterfactual。
11. fingerprint coverage 可度量。
12. frontend semantic accuracy 有独立 benchmark。
13. 新旧行为有明确 comparison report。
14. 所有核心参数有可解释名称和保存机制。

---

# 47. 明确禁止的实现捷径

Codex 执行时不要做以下事情：

### 禁止 1

不要为了“可微”把 AST/CFG/PDG 改成神经网络。

### 禁止 2

不要用一个 MLP 直接替代全部人工 feature 公式。

### 禁止 3

不要让优化器自动修改特征表达式。

### 禁止 4

不要继续把 threshold/prominence 作为训练前硬筛。

### 禁止 5

不要把 UNKNOWN 填成 0。

### 禁止 6

不要从现有 feature score 自动生成 Ground Truth。

### 禁止 7

不要只根据 random MATLAB syntax 生成训练集。

### 禁止 8

不要把 train/test 仅随机切分 renderer 变体。

### 禁止 9

不要在 Soft-DP 中显式枚举所有 segmentation。

### 禁止 10

不要删除 legacy path，直到 V2 通过 regression。

### 禁止 11

不要让训练和推理使用不同的能量定义。

### 禁止 12

不要无约束训练一堆强相关 scalar，造成 energy 任意缩放。

---

# 48. 推荐的第一批具体工作任务

Codex 应按以下顺序开始。

## Task 1

阅读并梳理当前：

```text
core/features.py
core/scoring.py
core/module_quality.py
core/completion.py
corpus/training.py
corpus/selection_tuning.py
corpus/generator.py
MATLAB frontend / flow / dependencies
```

生成：

```text
docs/V2_CURRENT_IMPLEMENTATION_MAP.md
```

只描述真实代码，不修改行为。

## Task 2

新增 Raw Fact Schema。

## Task 3

让 legacy features 从 Raw Facts 重建，证明行为一致。

## Task 4

新增 semantic oracle tests。

## Task 5

设计并实现 V2 continuous features。

## Task 6

连续化 module quality。

## Task 7

实现 Soft-DP + structured NLL。

## Task 8

实现 unified Torch trainer。

## Task 9

将 Hard-DP 改为使用同一 Energy API。

## Task 10

实现 Semantic Task Graph / Renderer / fingerprint tooling。

---

# 49. 第一阶段不要做的事情

第一阶段不要：

- 大规模抓取 GitHub MATLAB 项目；
- 追求最终 SOTA F1；
- 删除 legacy grid search；
- 改 CLI 用户接口；
- 过度设计复杂 neural scorer；
- 自动发明新 feature；
- 直接将所有 15 特征全部重写后一次提交。

应逐步提交，每阶段都保持测试通过。

---

# 50. 最终希望形成的 CodeSeam V2 定义

一句话：

> **CodeSeam V2 是一个基于静态程序语义 Raw Facts、人工设计连续可解释特征、可微结构化能量模型和 Soft-DP 训练的 MATLAB 代码模块边界识别系统；训练阶段通过 Ground Truth segmentation 的结构化负对数似然统一优化全部数值参数，工程阶段通过相同能量函数的 Hard-DP 生成确定性切点。**

数学上：

\[
r_i = \text{StaticFacts}(X,i)
\]

\[
\phi_i = \Phi(r_i;\theta_f)
\]

\[
B_i = B(\phi_i;w_f)
\]

\[
Q(a,b)=Q(r_{a:b};\theta_q)
\]

\[
E(C)
=
\sum_{i\in C}B_i
+
\sum_{M\in Seg(C)}Q(M)
-\lambda|C|
\]

训练：

\[
L
=
-E(C^*)
+
\log\sum_C e^{E(C)}
\]

通过 Soft-DP 高效计算。

推理：

\[
C_{hard}
=
\arg\max_C E(C)
\]

通过 Hard-DP 计算。

---

# 51. Codex 在任何存在歧义时的默认决策原则

如果实现过程中出现本文没有覆盖的细节，按以下优先级决策：

1. **优先保证静态分析事实正确。**
2. **优先保证可解释性。**
3. **优先保留连续数值信息，不做过早 hard filtering。**
4. **优先把不确定性显式化，而不是猜。**
5. **优先统一训练和推理 energy。**
6. **优先保持 legacy 行为可回归。**
7. **优先用最简单可解释公式，而不是复杂模型。**
8. **优先通过数据覆盖解决泛化，不要先增加模型复杂度。**
9. **遇到 Raw Fingerprint 相同但标签冲突时，优先怀疑缺失语义事实，而不是继续调优化器。**
10. **Ground Truth 必须来源于语义任务结构或人工标注，绝不能来源于 CodeSeam 自己的 feature。**

---

# 52. 交付要求

每个 Phase 完成时，Codex 应给出：

1. 修改文件列表；
2. 新增 API；
3. 被废弃但仍保留的 legacy API；
4. 数学定义变化；
5. 单元测试；
6. 回归结果；
7. 已知限制；
8. 下一阶段依赖；
9. 是否存在 breaking change；
10. 示例输入输出。

不要只提交代码而不说明行为变化。

---

# 53. 特别注意：研究逻辑与工程逻辑必须一致

本项目的研究逻辑不是：

```text
人为不断调规则直到 F1 高
```

而是：

```text
人工提供可解释语义假设
    ↓
固定公式
    ↓
数据学习数值参数
    ↓
结构化 Loss
    ↓
验证真实泛化
```

工程实现必须服务于这个研究逻辑。

如果某个修改只能通过：

```text
special case
if example_name == ...
```

或：

```text
if score > magic_number
```

提升当前 synthetic corpus 指标，而没有一般性语义理由，则不要接受。

---

# 54. 最终检查清单

在宣布 V2 重构完成前，逐项确认：

- [ ] Raw Facts 与 Features 已完全分层
- [ ] Static Analyzer 不需要 autograd
- [ ] Feature model 可微
- [ ] Feature 公式固定
- [ ] 只训练数值
- [ ] Completion 连续化
- [ ] Role transition 已进入 feature
- [ ] Dependency mass / long-range coupling 已进入 raw/feature
- [ ] Reliability/confidence 已进入模型
- [ ] Threshold 已从训练主路径移除
- [ ] Prominence 不再 hard-filter
- [ ] Module Quality 可微
- [ ] Segment Energy 定义统一
- [ ] Soft-DP 可训练
- [ ] Hard-DP 可推理
- [ ] Soft/Hard 使用同一参数
- [ ] Structured NLL 已实现
- [ ] Gradient check 通过
- [ ] Semantic Oracle Corpus 已建立
- [ ] Semantic Task Graph 已建立
- [ ] MATLAB Renderer 已建立
- [ ] Counterfactual generation 已建立
- [ ] Fingerprint coverage 可计算
- [ ] Collision / missing-feature report 可生成
- [ ] Train/Val/Test 防 semantic leakage
- [ ] Legacy 路径仍可运行
- [ ] V1 vs V2 comparison report 已生成
- [ ] 所有主要公式和参数已文档化

---

## 结束语

本轮重构的核心不是“换一个优化器”，而是把 CodeSeam 的学习问题重新定义清楚：

> **静态程序分析负责事实；可解释特征负责语义映射；结构化能量负责全局切分；Soft-DP 负责训练；Hard-DP 负责工程决策；Ground Truth 来自独立语义结构；数据集负责覆盖特征空间和打破错误相关性。**

后续实现中，任何局部设计如果违反这条主线，应优先重新评估，而不是为了兼容旧代码继续叠加规则。
