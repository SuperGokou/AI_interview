# 第三方组件与商业交付边界

本文件是交付清单，不是对第三方代码、模型或人物素材的再授权。

- 项目由 SuperGokou/AI_interview 演进。当前基线未发现根目录 LICENSE。仓库所有权不自动证明所有历史贡献均可商业再授权；交付方须确认来源与权利链，保留原有版权声明。
- 前端依赖以 package-lock.json 为准；Python 依赖以 requirements 文件为准。分发时保留各包许可证和通知。
- 浏览器人员检测使用 @mediapipe/tasks-vision 0.10.32（Apache-2.0）及 EfficientDet Lite0 模型。模型原地址：https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite 。模型文件和依赖许可证应随交付核验。
- 数字人形象、声音、开场/结束视频及生成素材：由项目方提供/生成。交付方需保存素材授权、生成服务商条款与肖像/声音使用授权证据；本仓库没有包含这些合同证明。
- deploy/gpu 为可选研发工具，涉及的模型、权重及依赖许可必须分别核验；不能因为工具脚本可用就承诺模型可无条件商业分发。
- 百炼及评分模型为外部服务，客户需使用自己的账号、API 密钥并承担计费；密钥不随源代码交付。

在权利链和客户验收完成之前，本版本应标记为待验收交付候选版，而非已经取得全部商业授权的成品。
