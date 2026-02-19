# 机器学习入门教程 / Machine Learning Tutorial

本教程介绍机器学习的基础概念和实践方法。This tutorial covers fundamental concepts and practical methods in machine learning.

## 什么是机器学习？

机器学习（Machine Learning）是人工智能的一个分支，它使计算机能够从数据中学习模式，而无需明确编程。

Machine learning is a branch of artificial intelligence that enables computers to learn patterns from data without being explicitly programmed.

### 主要类型 / Main Types

1. **监督学习 (Supervised Learning)**
   - 分类 Classification
   - 回归 Regression

2. **无监督学习 (Unsupervised Learning)**
   - 聚类 Clustering
   - 降维 Dimensionality Reduction

3. **强化学习 (Reinforcement Learning)**
   - 基于奖励的学习 Reward-based learning

## 线性回归示例 / Linear Regression Example

线性回归是最简单的机器学习算法之一。Linear regression is one of the simplest machine learning algorithms.

```python
import numpy as np
from sklearn.linear_model import LinearRegression

# 准备数据 Prepare data
X = np.array([[1], [2], [3], [4], [5]])
y = np.array([2, 4, 6, 8, 10])

# 创建并训练模型 Create and train model
model = LinearRegression()
model.fit(X, y)

# 预测 Make predictions
X_new = np.array([[6], [7]])
predictions = model.predict(X_new)
print(predictions)  # Output: [12. 14.]
```

## 数据预处理 / Data Preprocessing

数据预处理是机器学习流程中的关键步骤。Data preprocessing is a critical step in the machine learning pipeline.

### 特征缩放 / Feature Scaling

```python
from sklearn.preprocessing import StandardScaler

# 标准化特征 Standardize features
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)
```

### 处理缺失值 / Handling Missing Values

```python
from sklearn.impute import SimpleImputer

# 填充缺失值 Impute missing values
imputer = SimpleImputer(strategy='mean')
X_imputed = imputer.fit_transform(X)
```

## 模型评估 / Model Evaluation

评估模型性能对于理解其效果至关重要。Evaluating model performance is crucial for understanding its effectiveness.

### 分类指标 / Classification Metrics

```python
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

# 计算指标 Calculate metrics
accuracy = accuracy_score(y_true, y_pred)
precision = precision_score(y_true, y_pred)
recall = recall_score(y_true, y_pred)
f1 = f1_score(y_true, y_pred)

print(f"Accuracy: {accuracy:.2f}")
print(f"Precision: {precision:.2f}")
print(f"Recall: {recall:.2f}")
print(f"F1 Score: {f1:.2f}")
```

### 交叉验证 / Cross-Validation

交叉验证帮助评估模型的泛化能力。Cross-validation helps assess the model's generalization capability.

```python
from sklearn.model_selection import cross_val_score

# K折交叉验证 K-fold cross-validation
scores = cross_val_score(model, X, y, cv=5)
print(f"Cross-validation scores: {scores}")
print(f"Mean score: {scores.mean():.2f}")
```

## 深度学习入门 / Introduction to Deep Learning

深度学习使用神经网络处理复杂的模式识别任务。Deep learning uses neural networks for complex pattern recognition tasks.

```python
import tensorflow as tf
from tensorflow import keras

# 构建简单的神经网络 Build a simple neural network
model = keras.Sequential([
    keras.layers.Dense(64, activation='relu', input_shape=(10,)),
    keras.layers.Dense(32, activation='relu'),
    keras.layers.Dense(1, activation='sigmoid')
])

# 编译模型 Compile model
model.compile(
    optimizer='adam',
    loss='binary_crossentropy',
    metrics=['accuracy']
)

# 训练模型 Train model
# model.fit(X_train, y_train, epochs=10, batch_size=32)
```

## 最佳实践 / Best Practices

1. **数据分割**: 始终将数据分为训练集、验证集和测试集
   **Data Split**: Always divide data into training, validation, and test sets

2. **特征工程**: 创建有意义的特征可以显著提高模型性能
   **Feature Engineering**: Creating meaningful features can significantly improve model performance

3. **正则化**: 使用正则化技术防止过拟合
   **Regularization**: Use regularization techniques to prevent overfitting

4. **超参数调优**: 通过网格搜索或随机搜索优化超参数
   **Hyperparameter Tuning**: Optimize hyperparameters through grid search or random search

## 总结 / Conclusion

机器学习是一个广阔的领域，本教程只是入门。持续学习和实践是掌握机器学习的关键。

Machine learning is a vast field, and this tutorial is just the beginning. Continuous learning and practice are key to mastering machine learning.
