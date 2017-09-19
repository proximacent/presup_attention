
## Task
Given a sample text the model must predict if it contains a presupposition triggering. Pressupositions are triggered by keywords such as "also", "again". The keywords are removed since their position make the task easier.

## Models
We experiment with 3 models for presupposition triggering.

### 1. PairWiseAttn
The base model for all others. The input is encoded via an RNN.
We take all output states for a sample and compute matrix multiplication on itself,
giving us a pairwise matching score across all input pairs. We then produce two
matrices, one row softmax and a column softmax.

### 2. Attention-over-Attention
Building on the base model, we compute a column-wise average over the row-wise softmax matrix, giving us vector `c`. We compute the dot product of vector `c` with the column-wise softmax matrix, giving us a sum-attention vector `att-o-att`.
This is based on [Cui et al, 2017](https://arxiv.org/pdf/1607.04423.pdf)'s Attention-over-Attention model for cloze-style reading comprehension.
However, we do not implement the last step where a a word is predicted by summing over `att-o-att` vector. Our final layer is a fully connected layer between `c` and our two classes.

### 3. Convolution-over-Attention
Given the two normalized pair-wise matching score matrices, we convolve over these.
The intuition is to locate attention groupings which seems supported by qualitative analysis of our data.

Base settings:
```python
  # General hyper params
  hp = HParams(
    emb_trainable = False,
    batch_size    = 64,
    max_seq_len   = 60,
    max_epochs    = 20,
    early_stop    = 10,
    keep_prob     = 0.5,
    eval_every    = 300,
    num_classes   = 2,
    l_rate        = 0.001,
    cell_units    = 128,
    cell_type     = 'LSTMCell',
    optimizer     = 'AdamOptimizer'
  )

  # Hyper params for dense layers
  hp.update(
    dense_units = 64
  )
  # Hyper params for convnet
  hp.update(
    filt_height  = 3,
    filt_width   = 3,
    h_layers     = 0,
    h_units = self.dense_units,
    conv_strides = [1,2,2,1], #since input is "NHWC", no batch/channel stride
    padding      = "VALID",
    out_channels = 32
  )
```

## Results

### Dataset: WSJ
Model    | param      | value | acc   | epoch

### Dataset: Giga also on val
Base results: 75.31 on epoch 1
Model    | param         | value | acc   | epoch
---------|---------------|-------|-------|
ConvAttn | RNN units     | 256   | 76.01 | 1
ConvAttn | RNN units     | 512   | 69.51 | 3
ConvAttn | batch_norm    | yes   | 50.66 | 1
ConvAttn | h_layers      | 1     | 75.60 | 2
ConvAttn | fine tune emb | no    | 77.48 | 7
ConvAttn | fine tune emb | no    | 77.77 | 6
         | RNN units     | 256   |       |


### Dataset: Giga also on test
Base results: val 78.64, test 78.14, epoch 7
Model     | param         | value | val   | test  | epoch
----------|---------------|-------|-------|
ConvAttn  | RNN units     | 256   | 79.14 | 78.26 | 4
-ConvAttn  | RNN units     | 512   |75.12  | 74.54      |
ConvAttn  | batch_norm    | yes   |       |       |
ConvAttn  | h_layers      | 1     |       |       |
ConvAttn  | fine tune emb | no    |       |       |

