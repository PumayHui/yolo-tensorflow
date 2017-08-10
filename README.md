# 表格识别（table-detection）
表格识别任务：获取PDF文档，对PDF文档中的表格区域进行识别。主要将PDF转化为图片，使用yolo的神经网络方法进行建模，将识别问题转化为回归问题。



## 1. 数据预处理

每处理2000个图片，线程个数和时间消耗对比，可以观察到，使用线程个数不宜太多也不宜太少。

| 线程个数 | 消耗时间 |
| :--- | :--- |
| 1    | 17.6 |
| 2    | 12.0 |
| 5    | 8.6  |
| 10   | 8.5  |



table-detection的表格数据有193565张图片，约20万，进行训练集/验证集/测试集划分后，训练集183908张图片，验证集4874张图片，测试集4783张图片，由于训练集数量庞大，无法将所有图片一起载入内存，因此使用动态批处理的技术进行数据读取，主要过程如下：

1.  创建多个**生产者线程**，每个线程负责从原始数据中读取图片和标签，并且进行图片和标签的预处理过程，存入数据队列中，每个生产者线程将无限循环地进行数据地读取和预处理，保证数据队列一直是满地状态。
2.  创建一个**消费者线程**，该线程负责从数据队列中读取一个batch的数据，并且将该数据导入显存中进行模型的训练。

使用这种**生产者消费者动态批处理**的方法，可以不用等待所有数据都导入内存中再进行训练，也解决了由于数据量过大无法全部导入内存的问题。



## 2. 实验对比

### 2.1 table-v1

模型的输入数据是网络的输入是一个4维tensor，尺寸为(128, 256, 256, 3)，分别表示一批图片的个数128、图片的宽的像素点个数256、高的像素点个数256和信道个数3。首先使用多个卷积神经网络层进行图像的特征提取，卷积神经网络层的计算过程如下步骤：

1.  **卷积层1**：卷积核大小3\*3，卷积核移动步长1，卷积核个数16，池化大小2\*2，池化步长2，池化类型为最大池化，激活函数ReLU。
2.  **卷积层2**：卷积核大小3\*3，卷积核移动步长1，卷积核个数32，池化大小2\*2，池化步长2，池化类型为最大池化，激活函数ReLU。
3.  **卷积层3**：卷积核大小3\*3，卷积核移动步长1，卷积核个数64，池化大小2\*2，池化步长2，池化类型为最大池化，激活函数ReLU。
4.  **卷积层4**：卷积核大小3\*3，卷积核移动步长1，卷积核个数128，池化大小2\*2，池化步长2，池化类型为最大池化，激活函数ReLU。
5.  **卷积层5**：卷积核大小3\*3，卷积核移动步长1，卷积核个数256，池化大小2\*2，池化步长2，池化类型为最大池化，激活函数ReLU。
6.  **卷积层6**：卷积核大小3\*3，卷积核移动步长1，卷积核个数512，池化大小2\*2，池化步长2，池化类型为最大池化，激活函数ReLU。
7.  **卷积层7**：卷积核大小3\*3，卷积核移动步长1，卷积核个数1024，池化大小2\*2，池化步长2，池化类型为最大池化，激活函数ReLU。
8.  **卷积层8**：卷积核大小3\*3，卷积核移动步长1，卷积核个数1024，池化大小2\*2，池化步长2，池化类型为最大池化，激活函数ReLU。
9.  **全连接层**：隐藏层单元数1274 （7\*7\*(1+5\*5)，7表示cell尺寸，1表示分类个数为1，5表示5个box，5表示4个坐标及confidence），激活函数sigmoid。

参数初始化：所有权重向量使用truncated_normal(0.0, sqrt(2/n))，所有偏置向量使用constant(0.0)，

使用yolo中提出的目标函数，如下图，使用Adam梯度下降法进行参数更新，学习率设为固定值0.00001，coord_scala设定为10，object_scala设定为10，nobject_scala设定为5，class_scala设定为1，batch_size设定为32。

![objective](/others/pictures/objective.png)

根据上述进行训练，收敛图如下，最终可以获得如下的训练/验证/测试的观察值：

-   训练速度：平均每秒训练25张图片，即训练50万个batch需要7.4天。
-   训练误差：
-   测试集IOU：
-   测试集识别召回率：
-   测试集识别错误率：
