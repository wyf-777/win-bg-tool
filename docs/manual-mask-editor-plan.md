# 手动修补 / 圈选抠图方案

状态：v1 已实现  
日期：2026-07-29  
目标项目：win-bg-tool  
建议项目内位置：`docs/manual-mask-editor-plan.md`

## 1. 背景

当前项目已经具备本机模型抠图、透明预览、导出、复制、拖出、多图灯箱等主路径能力。下一步要解决的问题是：模型偶尔会多抠、少抠，用户需要一种低成本方式手动修正结果。

本功能不做成完整修图软件，而是做成轻量的“修补模式”：在模型结果基础上，通过圈选区域来删除、恢复或只保留用户指定部分。

## 2. 用户已确认的产品决策

1. 交互方式：圈选后点按钮执行。
2. 恢复选区：默认完全恢复原图内容，边缘通过羽化过渡。
3. 当前版本提供矩形、圆形、椭圆、自由套索、多边形套索和画笔六种选区工具，画笔用于局部补抠与擦除。
4. 入口放在结果出来后的底部操作区，命名倾向“修补”。
5. 界面要求：简洁、大方、美观，布局合理。
6. “保留选区”采用直觉型语义：只保留这次圈出的区域，圈外全部透明；删除/恢复则基于当前结果继续修补。

## 3. 成熟软件参考

### 3.1 Photoshop：选区羽化与蒙版细化

Photoshop 对选区边缘的成熟做法是“羽化半径”。用户可以在套索/矩形等选区工具的选项栏输入 Feather 值，也可以对已有选区使用 `Select > Modify > Feather` 并输入 Feather Radius。

可借鉴点：

- 羽化作为选区属性，而不是单独滤镜。
- 羽化用像素半径表达，用户易理解。
- 已有选区也可以后处理羽化。
- 边缘调整应有预览，避免用户猜结果。

参考：

- Adobe Photoshop - Define feathered edges for selections  
  https://helpx.adobe.com/photoshop/desktop/make-selections/refine-modify-selections/define-feathered-edges.html
- Adobe Photoshop - Refine your selection and mask  
  https://helpx.adobe.com/photoshop/desktop/make-selections/refine-modify-selections/refine-your-selection-and-mask.html
- Adobe Photoshop - Add layer masks  
  https://helpx.adobe.com/photoshop/desktop/create-masks/layer-masks/add-layer-masks.html

### 3.2 Photoshop：Remove Background 后仍需要手动修蒙版

Photoshop 的 Remove Background 会自动隔离主体并生成透明背景或蒙版层；官方也提示，如果结果不完美，可以在 layer mask 上手动 refine。

可借鉴点：

- 自动抠图和手动修补不是互斥关系，成熟产品也把手动修补作为自动结果的补充。
- 我们不需要暴露复杂图层系统，但应在内部把抠图结果视为“可编辑 alpha mask”。

参考：

- Adobe Photoshop - Remove background in your images  
  https://helpx.adobe.com/photoshop/desktop/repair-retouch/remove-objects-fill-space/remove-background-in-your-images.html

### 3.3 GIMP：Feather / Sharpen 是 selection channel 的边缘处理

GIMP 的 Feather 命令会让选区边缘与周围产生平滑过渡，用户输入的是选区边缘羽化宽度，默认单位为像素。GIMP 也有 Sharpen 作为反向能力，用来减少选区边缘模糊。

可借鉴点：

- 技术实现上，可以把选区当作一张灰度 mask。
- 羽化本质是让黑白选区变成灰度过渡区。
- 需要支持 0 px 硬边，适合图标、商品、硬边物体。

参考：

- GIMP - Feather  
  https://docs.gimp.org/2.10/en/gimp-selection-feather.html
- GIMP - Sharpen selection  
  https://docs.gimp.org/2.10/en/gimp-selection-sharpen.html

### 3.4 Adobe Express：Erase / Restore / Reset / Invert 的轻量产品模型

Adobe Express 的 Erase 工具提供 Quick Selection 和 Circle Brush，可调 Size、Hardness、Opacity；如果删多了，用 Restore 画回来；还有 Reset 和 Invert。

可借鉴点：

- 工具语义应非常直接：Erase / Restore / Reset / Invert。
- 第一版可以不用画笔，但按钮命名应靠近用户直觉：删除、恢复、保留。
- 需要撤销，用户才敢试。
- Invert 的思想可借鉴到“保留选区”：圈出要的，反向清掉圈外。

参考：

- Adobe Express - Erase unwanted parts of an image  
  https://helpx.adobe.com/uk/express/web/image-creation-and-editing/edit-images/eraser.html
- Adobe Express - Remove background from images  
  https://helpx.adobe.com/express/web/image-creation-and-editing/edit-images/remove-background.html

## 4. 推荐第一版范围

### 4.1 必须做

- 单图结果可进入“修补模式”。
- 多图灯箱中可对当前图片进入“修补模式”。
- 支持矩形选区。
- 支持圆形和椭圆选区。
- 支持自由套索选区。
- 支持多边形套索，逐点描边后闭合选区。
- 支持可调大小的画笔选区。
- 圈选后点按钮执行。
- 操作按钮：保留选区、删除选区、恢复选区。
- 羽化滑块：默认 4 px，范围 0-24 px。
- 撤销 / 重做。
- 应用后更新当前结果图；导出、复制、拖出都使用修补后的结果。
- 取消/返回时不破坏已有结果。

### 4.2 暂不做

- 智能边缘吸附。
- 发丝级 Refine Hair。
- 批量套用同一个修补动作。
- 图层系统。
- 非破坏性 mask 历史长期保存到工程文件。

## 5. 产品交互设计

### 5.1 入口

结果出来后，底部操作区增加一个按钮：`修补`。

进入修补后，主窗口直接切换到全窗口修补页，不弹出独立对话框；完成或取消后回到之前的主界面状态。

单图：

- `打开` / `清除` / `修补` / `导出 PNG`

多图灯箱：

- 当前图完成后显示 `修补`。
- 修补只作用于当前图。

### 5.2 修补页布局

顶部只保留窄命令栏：返回、居中的当前文件名和完成。撤销、选区和查看控制不再挤在顶部，避免小窗口进入修补时按钮相互挤压。

左侧是可独立滚动的连续工具栏，画布占用其余空间。工具按使用语境分组：

- 工具：矩形 / 圆形 / 椭圆 / 自由套索 / 多边形套索 / 画笔。多边形套索单击添加锚点，双击、Enter 或点回第一个锚点闭合；Backspace 回退一个锚点，Esc 取消当前描边。
- 选中画笔时才显示 4-120 px 笔径滑块，默认 32 px；已有画笔选区保存创建时的笔径，不会被之后的滑块修改。
- 边缘：羽化滑块和当前数值。对最后一次已应用修补，继续调节羽化会即时重算该操作的边缘，无需重新圈选；开始新的选区后，滑块用于下一次操作。
- 查看：`结果` / `叠加` / `原图`。默认“叠加”：原图以 38% 透明度作为底图，当前结果完整叠在上方；透明区域会露出原图轮廓，便于定位漏抠内容。仅在“叠加”时显示 0-100% 强度滑块；“结果”保留干净的透明棋盘格预览，“原图”用于确认主体边界。
- 历史：撤销 / 重做；操作：保留选区 / 删除选区 / 恢复选区 / 清除选区。

画布在右侧始终优先保持可用面积；窗口高度不足时只有左栏滚动，不压缩顶部命令栏或让底部操作区堆叠。

### 5.3 操作语义

#### 保留选区

适合用户想“只要圈出来的主体”。

规则：

- 基于这次选区一键重置 alpha。
- 选区中心 alpha = 当前结果 alpha 或 255，建议第一版使用当前结果 alpha，以保留模型边缘质量。
- 圈外 alpha = 0。
- 羽化区按灰度过渡。

推荐算法：

- 生成选区 mask：中心 255，圈外 0。
- 对 mask 做 GaussianBlur(radius=feather)。
- 新 alpha = 当前结果 alpha * feathered_selection_mask / 255。

#### 删除选区

适合去掉模型多抠出来的杂物。

规则：

- 基于当前修补后的结果继续操作。
- 选区中心 alpha = 0。
- 羽化区逐渐从当前 alpha 过渡到 0。

推荐算法：

- feathered_selection_mask = 0-255。
- new_alpha = current_alpha * (255 - feathered_selection_mask) / 255。

#### 恢复选区

适合补回模型漏掉的主体部分。

规则：

- 基于当前修补后的结果继续操作。
- 选区中心 RGB 使用原图，alpha = 255。
- 羽化区从当前结果逐渐混合到原图不透明内容。

推荐算法：

- feathered_selection_mask = 0-255。
- new_rgb = blend(current_rgb, original_rgb, feathered_selection_mask / 255)。
- new_alpha = max(current_alpha, feathered_selection_mask)。
- 选区中心会完全恢复，边缘自然过渡。

## 6. 羽化默认值

推荐默认：4 px。

范围：0-24 px。

理由：

- 0 px：硬边，适合图标、商品、UI 素材。
- 3-6 px：普通照片常用，能避免明显硬边。
- 8-16 px：适合大图或柔边主体。
- 24 px：作为上限，避免小图上过度糊边。

成熟软件经验：Photoshop 和 GIMP 都把羽化表达为像素半径/宽度，用户可以按图像尺度调节；我们沿用这个模型，降低学习成本。

## 7. 技术设计

### 7.1 新增逻辑层

建议新增：

- `app/services/mask_edit.py` 或 `app/editing/mask_editor.py`

职责：

- 接收 original_image / current_result_image。
- 根据选区生成 mask。
- 执行 keep / erase / restore。
- 维护 undo / redo 栈。
- 返回新的 PIL RGBA result_image。

建议核心类型：

- `SelectionShape`
- `RectSelection`
- `LassoSelection`
- `MaskEditOperation`
- `MaskEditState`

### 7.2 新增 UI 层

建议新增：

- `app/ui/mask_editor.py`

职责：

- 绘制修补页。
- 鼠标拖拽生成矩形、圆形、椭圆、自由套索或画笔路径；多边形套索以单击逐点生成路径。
- 预览选区边框和遮罩。
- 将屏幕坐标转换为图像坐标。
- 调用逻辑层生成新结果。

### 7.3 坐标换算

当前预览通常是保持比例缩放居中显示，需要记录：

- image_size
- preview_widget_size
- scaled_pixmap_size
- offset_x / offset_y
- scale

鼠标点转换：

- image_x = (mouse_x - offset_x) / scale
- image_y = (mouse_y - offset_y) / scale

所有点需要 clamp 到图像范围内。

### 7.4 撤销/重做

第一版建议按结果图快照做，不做复杂操作日志。

- undo_stack 保存 PIL RGBA result_image copy。
- redo_stack 保存 PIL RGBA result_image copy。
- 每次执行 keep / erase / restore 前，把当前结果压入 undo。
- undo 后刷新预览。

为控制内存：

- 最多保存 20 步。
- 大图可后续改为只保存 alpha mask 或差异 patch。

## 8. 与现有项目的接入点

### 8.1 MainWindow

新增 `repair_current_result()` 或类似 slot。

入口逻辑：

- 单图：取 session 中唯一 DONE item。
- 多图灯箱：取当前 lightbox item。
- 没有完成结果时禁用或提示。

### 8.2 ImageItem

当前 `ImageItem` 已持有：

- source_path
- result_image
- result_path
- status

第一版不一定要改数据模型，只需修补完成后更新：

- item.result_image = edited_image
- 重新写临时 result_path
- workspace.update_item(item)

### 8.3 Workspace / Lightbox

修补完成后：

- 单图刷新 DropCanvas。
- 多图刷新对应 tile。
- 如果在灯箱中，刷新当前灯箱预览。

## 9. 风险与规避

### 9.1 选区坐标不准

风险：预览缩放、居中、棋盘格合成后，鼠标坐标映射到原图会偏。

规避：

- 抽出统一的 `ImageViewportTransform`。
- 单测覆盖不同图片比例、窗口比例、缩放后的点映射。

### 9.2 恢复选区边缘发白或发黑

风险：透明结果的 RGB 可能已有无意义颜色，直接混合会产生边缘脏色。

规避：

- 恢复时 RGB 以原图为目标。
- 删除只改 alpha，不乱改 RGB。
- 导出非透明格式时继续用现有白底 flatten。

### 9.3 大图撤销占内存

风险：20 步全图快照在大图上占内存。

规避：

- 第一版限制撤销步数 10-20。
- 后续改成只保存 alpha mask 或局部 patch。

### 9.4 UI 变复杂

风险：项目本来是轻量工具，修补功能容易变成修图软件。

规避：

- 保持为矩形/圆形/椭圆/自由套索/多边形套索/画笔 + 三个动作 + 羽化 + 撤销。
- 不加入图层、复杂边缘参数。
- 主界面只多一个“修补”入口。

### 9.5 透明结果难以定位漏抠内容

风险：单独查看透明结果时，用户无法判断漏掉的主体原本位于哪里，恢复选区容易偏移。

规避：

- 修补页默认使用叠加参考视图，原图淡显，结果完整显示。
- 保留结果和原图两个直接查看方式，分别适合删除杂物和确认边界。
- 三种查看方式只改变绘制，不改变选区坐标或当前修补结果。

## 10. 验收标准

### 功能验收

- 单图抠图完成后可进入修补。
- 多图灯箱当前图可进入修补。
- 矩形选区可见且坐标准确。
- 圆形拖拽始终保持等宽高，椭圆按拖拽边界生成。
- 套索选区可见且自动闭合。
- 多边形套索可暂停后继续添加锚点，并可通过双击、Enter 或首点闭合。
- 画笔单击和拖拽均能生成可见选区。
- 删除选区能让选区中心透明。
- 恢复选区能把原图内容恢复为不透明。
- 保留选区能让圈外透明。
- 羽化 0 px 为硬边。
- 羽化 4 px 有自然过渡。
- 已应用操作后可调整其羽化值，结果和撤销记录保持正确。
- 撤销/重做可用。
- 完成后导出/复制/拖出使用修补后的结果。

### 体验验收

- 修补页简洁，不像复杂修图软件。
- 操作按钮文案清楚。
- 没有选区时，三个动作按钮禁用或提示“请先圈选区域”。
- Esc 不误丢修补结果；未应用返回前有确认或保留当前编辑状态。

### 测试建议

- `mask_edit` 纯函数单测。
- 坐标换算单测。
- 透明/不透明 alpha 运算单测。
- 小图、横图、竖图、大图人工烟测。

## 11. 推荐实施顺序

1. 做 `mask_edit` 纯逻辑层和单测。
2. 做矩形选区 UI。
3. 接入单图修补入口。
4. 做删除 / 恢复 / 保留三动作。
5. 加羽化滑块。
6. 加撤销 / 重做。
7. 接入多图灯箱当前图。
8. 做视觉打磨和烟测。

## 12. 最终建议

这个功能值得做，而且应作为 M6 中优先级最高的体验增强之一。它直接解决模型质量不稳定带来的真实痛点，比在线 remove.bg、GPU、打包更贴近当前产品的核心价值。

第一版不要追求专业修图工具的完整性，要追求：用户发现模型抠错了，能在 10 秒内圈一下、点一下、修好。

## 13. 实现记录

2026-07-29 已完成 v1：

- 主界面结果操作区增加“修补”入口；多图时优先修补灯箱当前图，也支持仅选中一张已完成图片后修补。
- 提供矩形和套索选区、0-24 px 羽化（默认 4 px）、保留/删除/恢复选区，以及 15 步撤销/重做。
- 已补充画笔选区，支持 4-120 px 笔径（默认 32 px）；笔径在开始绘制时固定，后续调节不会改变已有笔迹。
- 已补充圆形和椭圆选区，和矩形、套索、画笔共用现有操作和羽化蒙版。
- 已补充多边形套索，用于沿不规则边缘逐点描边，闭合前不会执行修改操作。
- 叠加参考视图支持 0-100% 原图强度调节，默认 38%。
- 羽化支持回调最后一次修补：调整值会重算该次操作的边缘，不需要重新圈选。
- 修补器已改为主窗口内页面，不再创建独立弹窗；完成写回结果，取消则保留原结果。
- 修补完成后替换当前会话结果和临时 PNG，因此导出、复制、拖出自动使用修补后的图像。
- 已覆盖蒙版生成、保留、删除、恢复、撤销重做的自动测试，并做过离屏 Qt 框选交互验证。

2026-07-29 已补充查看方式：

- 修补预览新增“结果” / “叠加” / “原图”；默认“叠加”，以 38% 透明度的原图辅助定位透明区域中的漏抠内容。
