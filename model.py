# Author: Andre Cianflone
import numpy as np
from pydoc import locate
import tensorflow as tf

# Global numerical types
floatX = tf.float32
intX = tf.int32

class CNN(object):
  """
  Some of the code for the CNN from Denny Britz:
  https://github.com/dennybritz/cnn-text-classification-tf/blob/master/text_cnn.py
  """
  def __init__(self, params, embedding, postag_size):

    global hp
    hp = params

    num_classes = 2
    vocab_size, _ = embedding.shape
    sequence_length = hp.max_seq_len
    filter_sizes = [3,4,5]
    num_filters = 128
    l2_reg_lambda=0.0

    # Embedding tensor is of shape [vocab_size x embedding_size]
    self.embedding_tensor = self.embedding_setup(embedding, hp.emb_trainable)

    # helper variable to keep track of steps
    self.global_step = tf.Variable(0, name='global_step', trainable=False)

    # Placeholders for input, output and dropout
    self.rnn_in_keep_prob  = tf.placeholder(floatX)
    self.mode = tf.placeholder(tf.bool, name="mode") # 1 stands for training
    self.input_len = tf.placeholder(intX, shape=[None,])
    self.postags = tf.placeholder(intX, shape=[None, hp.max_seq_len])

    self.inputs = tf.placeholder(tf.int32, [None, sequence_length], name="inputs")
    self.labels = tf.placeholder(tf.float32, [None, num_classes], name="labels")
    self.keep_prob = tf.placeholder(tf.float32, name="keep_prob")

    self.batch_size = tf.shape(self.inputs)[0]

    # Keeping track of l2 regularization loss (optional)
    l2_loss = tf.constant(0.0)

    # Embedding layer
    self.embedded = self.embedded(self.inputs, self.postags, postag_size, self.embedding_tensor)
    self.embedded = tf.expand_dims(self.embedded, -1)
    self.embedding_size = self.embedded.shape[2].value

    # Create a convolution + maxpool layer for each filter size
    pooled_outputs = []
    for i, filter_size in enumerate(filter_sizes):
      with tf.name_scope("conv-maxpool-%s" % filter_size):
        # Convolution Layer
        filter_shape = [filter_size, self.embedding_size, 1, num_filters]
        W = tf.Variable(tf.truncated_normal(filter_shape, stddev=0.1), name="W")
        b = tf.Variable(tf.constant(0.1, shape=[num_filters]), name="b")
        conv = tf.nn.conv2d(
          self.embedded,
          W,
          strides=[1, 1, 1, 1],
          padding="VALID",
          name="conv")
        # Apply nonlinearity
        h = tf.nn.relu(tf.nn.bias_add(conv, b), name="relu")
        # Maxpooling over the outputs
        pooled = tf.nn.max_pool(
          h,
          ksize=[1, sequence_length - filter_size + 1, 1, 1],
          strides=[1, 1, 1, 1],
          padding='VALID',
          name="pool")
        pooled_outputs.append(pooled)

    # Combine all the pooled features
    num_filters_total = num_filters * len(filter_sizes)
    self.h_pool = tf.concat(pooled_outputs, 3)
    self.h_pool_flat = tf.reshape(self.h_pool, [-1, num_filters_total])

    # Add dropout
    with tf.name_scope("dropout"):
      self.h_drop = tf.nn.dropout(self.h_pool_flat, self.keep_prob)

    # Final (unnormalized) scores and predictions
    with tf.name_scope("output"):
      W = tf.get_variable(
        "W",
        shape=[num_filters_total, num_classes],
        initializer=tf.contrib.layers.xavier_initializer())
      b = tf.Variable(tf.constant(0.1, shape=[num_classes]), name="b")
      l2_loss += tf.nn.l2_loss(W)
      l2_loss += tf.nn.l2_loss(b)
      self.scores = tf.nn.xw_plus_b(self.h_drop, W, b, name="scores")
      self.predictions = tf.argmax(self.scores, 1, name="predictions")

    # Calculate mean cross-entropy loss
    with tf.name_scope("loss"):
      losses = tf.nn.softmax_cross_entropy_with_logits(logits=self.scores, labels=self.labels)
      self.cost = tf.reduce_mean(losses) + l2_reg_lambda * l2_loss

    # Predictions
    self.y_prob, self.y_pred, self.y_true = self.predict(self.labels, self.scores)


    # Optimize
    self.optimize = self.optimize_step(self.cost,self.global_step)

  def embedded(self, word_ids, postags, postag_size, embedding_tensor, scope="embedding"):
    """Swap ints for dense embeddings, on cpu.
    word_ids correspond the proper row index of the embedding_tensor

    Args:
      words_ids: array of [batch_size x sequence of word ids]
      embedding_tensor: tensor from which to retrieve the embedding, word id
        takes corresponding tensor row
    Returns:
      tensor of shape [batch_size, sequence length, embedding size]
    """
    with tf.variable_scope(scope):
      with tf.device("/cpu:0"):
        inputs = tf.nn.embedding_lookup(embedding_tensor, word_ids)

    # Maybe concat word embeddings with one-hot pos tags
    if hasattr(hp, 'postags') and hp.postags:
      tags = tf.one_hot(postags, postag_size)
      inputs = tf.concat([inputs, tags], axis=2)
    return inputs

  def embedding_setup(self, embedding, emb_trainable):
    """ If trainable, returns variable, otherwise the original embedding """
    if emb_trainable == True:
      emb_variable = tf.get_variable(
          name="embedding_matrix", shape=embedding.shape,
          initializer = tf.constant_initializer(embedding))
      return emb_variable
    else:
      return embedding

  def predict(self, labels, logits):
    """ Returns class label (int) for prediction and gold
    Args:
      pred_logits : predicted logits, not yet softmax
      classes : labels as one-hot vectors
    """
    y_prob = tf.nn.softmax(logits)
    y_pred = tf.argmax(y_prob, axis=1)
    y_true = tf.argmax(labels, axis=1)

    return y_prob, y_pred, y_true

  def optimize_step(self, loss, glbl_step):
    """ Locate optimizer from hp, take a step """
    Opt = locate("tensorflow.train." + hp.optimizer)
    if Opt is None:
      raise ValueError("Invalid optimizer: " + hp.optimizer)
    optimizer = Opt(hp.l_rate)
    grads_vars = optimizer.compute_gradients(loss)
    capped_grads = [(None if grad is None else tf.clip_by_value(grad, -1., 1.), var)\
                                                  for grad, var in grads_vars]
    take_step = optimizer.apply_gradients(capped_grads, global_step=glbl_step)
    return take_step

class RNN_base():
  """
  Base RNN model
  """
  def __init__(self,params, embedding, postag_size):
    """
    Args:
      params: hyper param instance
    """
    global hp
    hp = params

    # helper variable to keep track of steps
    self.global_step = tf.Variable(0, name='global_step', trainable=False)

    ############################
    # Inputs
    ############################
    self.keep_prob = tf.placeholder(floatX)
    self.rnn_in_keep_prob  = tf.placeholder(floatX)
    self.mode = tf.placeholder(tf.bool, name="mode") # 1 stands for training
    self.vocab_size, _ = embedding.shape
    # Embedding tensor is of shape [vocab_size x embedding_size]
    self.embedding_tensor = self.embedding_setup(embedding, hp.emb_trainable)

    # RNN inputs
    self.inputs = tf.placeholder(intX, shape=[None, hp.max_seq_len])
    self.postags = tf.placeholder(intX, shape=[None, hp.max_seq_len])
    self.embedded = self.embedded(self.inputs, self.postags, postag_size, self.embedding_tensor)
    self.emb_size = self.embedded.shape[2].value
    # self.embedded = tf.layers.batch_normalization(embedded, training=self.mode)
    self.input_len = tf.placeholder(intX, shape=[None,])

    # Targets
    self.labels = tf.placeholder(intX, shape=[None, hp.num_classes])

    self.batch_size = tf.shape(self.inputs)[0]

    ############################
    # Encode input with RNN
    ############################

    # Forward/backward cells
    if hp.birnn==True:
      self.encoder_h_size = hp.cell_units * 2
      cell_fw, cell_bw = self.build_cell(birnn=True)
      # Get encoded inputs
      self.encoded_outputs, self.encoded_state = self.bi_rnn_encode(
                               self.embedded, self.input_len,cell_fw, cell_bw)
    else:
      self.encoder_h_size = hp.cell_units
      cell = self.build_cell(birnn=False)
      # Get encoded inputs
      self.encoded_outputs, self.encoded_state = self.rnn_encode(
                                         self.embedded, self.input_len,cell)

    if hp.parallel==True:
      cell_emb = self.build_cell(birnn=False)
      # Get encoded inputs
      self.encoded_outputs_emb, self.encoded_state_emb = self.rnn_encode(
                         self.embedded, self.input_len,cell, scope="rnn_emb")

    # Word gate
    if hp.word_gate == True:
      self.encoded_outputs = self.word_gate(\
                          self.embedded, self.input_len, self.encoded_outputs)

    # Pair-wise score
    self.p_w = self.pair_wise_matching(self.encoded_outputs)

    # Attn matrices
    self.col_attn, self.row_attn = self.attn_matrices(self.p_w, self.input_len,
                                                          self.batch_size)
    # Default logits
    self.logits = self.get_logits(self.col_attn,self.row_attn)
    # self.logits = None
    ############################
    # Loss/Optimize
    ############################
    # Build loss
    self.loss = self.classification_loss(self.labels, self.logits)
    self.cost = tf.reduce_mean(self.loss) # average across batch

    # Predictions
    self.y_prob, self.y_pred, self.y_true = self.predict(self.labels, self.logits)

    # Optimize
    self.optimize = self.optimize_step(self.cost,self.global_step)

  def word_gate(self, embedded, input_len, encoded_outputs):
    """
    To increase sparsity in the attention layer, jointly learn to drop words
    that never contribute to presup triggering, such as stop words?
    """
    # Reshape to rank 2 tensor so timestep is no longer a dimension
    enc_shape = tf.shape(encoded_outputs)
    embedded = tf.reshape(embedded, [-1, self.emb_size])
    encoded_outputs  = tf.reshape(encoded_outputs, [-1, self.encoder_h_size])

    # Word gate
    gate = dense(embedded, self.emb_size, self.encoder_h_size, 'word_gate',
	act=tf.nn.sigmoid)
    gate = tf.nn.dropout(gate, self.keep_prob)
    gated = tf.multiply(gate, encoded_outputs)

    # Reshape back to the original tensor shape
    gated = tf.reshape(gated, enc_shape)
    return gated

  def embedded(self, word_ids, postags, postag_size, embedding_tensor, scope="embedding"):
    """Swap ints for dense embeddings, on cpu.
    word_ids correspond the proper row index of the embedding_tensor

    Args:
      words_ids: array of [batch_size x sequence of word ids]
      embedding_tensor: tensor from which to retrieve the embedding, word id
        takes corresponding tensor row
    Returns:
      tensor of shape [batch_size, sequence length, embedding size]
    """
    with tf.variable_scope(scope):
      with tf.device("/cpu:0"):
        inputs = tf.nn.embedding_lookup(embedding_tensor, word_ids)

    # Maybe concat word embeddings with one-hot pos tags
    if hasattr(hp, 'postags') and hp.postags:
      tags = tf.one_hot(postags, postag_size)
      inputs = tf.concat([inputs, tags], axis=2)
    return inputs

  def embedding_setup(self, embedding, emb_trainable):
    """ If trainable, returns variable, otherwise the original embedding """
    if emb_trainable == True:
      emb_variable = tf.get_variable(
          name="embedding_matrix", shape=embedding.shape,
          initializer = tf.constant_initializer(embedding))
      return emb_variable
    else:
      return embedding

  def build_cell(self, cell_type="LSTMCell", birnn=True):
    # Cells initialized with scope initializer
    with tf.variable_scope("Cell", initializer=tf.orthogonal_initializer):
      Cell = locate("tensorflow.contrib.rnn." + cell_type)
      if Cell is None:
        raise ValueError("Invalid cell type " + cell_type)
      cell_fw = self.drop_wrap(Cell(hp.cell_units))

      # If unidirectional, return only forward
      if birnn==False:
        return cell_fw

      cell_bw = self.drop_wrap(Cell(hp.cell_units))
      return cell_fw, cell_bw

  def pair_wise_matching(self, rnn_h):
    """
    Returns pair-wise matching matrix of shape [batch_size, time, time]
    Args:
      rnn_h: rnn hidden states over time (output of dynamic encoder)
    """
    # Since rnn_h is [batch_size, time, h_size], transpose 2 and 1 dim
    x = tf.transpose(rnn_h, perm=[0, 2, 1])
    # Output of matmul should be [batch_size, time,time]
    p_w = tf.matmul(rnn_h,x)
    return p_w

  def attn_matrices(self, p_w, input_len, batch_size):
    """
    Create column-wise and row-wise softmax, masking 0
    Based on https://arxiv.org/abs/1607.04423
    """
    # Softmax over 2nd dim
    rows = tf.nn.softmax(p_w, dim=1)
    # Softmax over 3rd dim
    cols = tf.nn.softmax(p_w, dim=2)

    return rows, cols

  def drop_wrap(self, cell):
    """ adds dropout to a recurrent cell """
    cell = tf.contrib.rnn.DropoutWrapper(\
          cell                  = cell,
          input_keep_prob       = self.rnn_in_keep_prob,
          variational_recurrent = hp.variational_recurrent,
          dtype                 = floatX,
          input_size            = self.emb_size)
    return cell

  def rnn_encode(self, x, seq_len, cell_fw, init_state=None, scope="unidirectionalRNN"):
    """
    Dynamic bidirectional encoder. For each x in the batch, the outputs beyond
    seq_len will be zeroed out.
    Args:
      cell: forward cell
      x: inputs to encode
      seq_len : length of each row in x batch tensor, needed for dynamic_rnn
    Returns:
      outputs: Tensor of shape [batch,time,units]
      state: last hidden state
    """
    # Output is the outputs at all time steps, state is the last state
    with tf.variable_scope(scope):
      # Unidirectional or bidirectional RNN
      outputs, state = tf.nn.dynamic_rnn(\
            cell=cell_fw,
            inputs=x,
            sequence_length=seq_len,
            initial_state=init_state,
            dtype=floatX)

    return outputs, state

  def bi_rnn_encode(self, x, seq_len, cell_fw, cell_bw=None, init_state_fw=None,
                  init_state_bw=None):
    """
    Dynamic bidirectional encoder. For each x in the batch, the outputs beyond
    seq_len will be zeroed out.
    Args:
      cell_fw: forward cell
      cell_bw: backward cell
      x: inputs to encode
      seq_len : length of each row in x batch tensor, needed for dynamic_rnn
    Returns:
      outputs: Tensor, result of the concatenation of
        tuple(output_fw, output_bw) of shape [batch,time,units]
      state: tuple(output_state_fw, output_state_bw) containing the forward
             and the backward final states of bidirectional rnlast hidden state
    """
    # Output is the outputs at all time steps, state is the last state
    with tf.variable_scope("biRNN"):
      # Unidirectional or bidirectional RNN
      if cell_bw==None:
        outputs, state = tf.nn.dynamic_rnn(\
            cell=cell_fw,
            inputs=x,
            sequence_length=seq_len,
            initial_state=init_state_fw,
            dtype=floatX)
      else:
        outputs, state = tf.nn.bidirectional_dynamic_rnn(\
                    cell_fw=cell_fw,
                    cell_bw=cell_bw,
                    inputs=x,
                    sequence_length=seq_len,
                    initial_state_fw=init_state_fw,
                    initial_state_bw=init_state_bw,
                    dtype=floatX)

      # outputs: a tuple(output_fw, output_bw), all sequence hidden states,
      # each as tensor of shape [batch,time,units]
      # Since we don't need the outputs separate, we concat here
      outputs = tf.concat(outputs,2)
      outputs.set_shape([None, None, self.encoder_h_size])
      # If LSTM cell, then "state" is not a tuple of Tensors but an
      # LSTMStateTuple of "c" and "h". Need to concat separately then new
      if "LSTMStateTuple" in str(type(state[0])):
        c = tf.concat([state[0][0],state[1][0]],axis=1)
        h = tf.concat([state[0][1],state[1][1]],axis=1)
        state = tf.contrib.rnn.LSTMStateTuple(c,h)
      else:
        state = tf.concat(state,1)
        # Manually set shape to Tensor or all hell breaks loose
        state.set_shape([None, self.encoder_h_size])
    return outputs, state

  def optimize_step(self, loss, glbl_step):
    """ Locate optimizer from hp, take a step """
    Opt = locate("tensorflow.train." + hp.optimizer)
    if Opt is None:
      raise ValueError("Invalid optimizer: " + hp.optimizer)
    optimizer = Opt(hp.l_rate)
    grads_vars = optimizer.compute_gradients(loss)
    capped_grads = [(None if grad is None else tf.clip_by_value(grad, -1., 1.), var)\
                                                  for grad, var in grads_vars]
    take_step = optimizer.apply_gradients(capped_grads, global_step=glbl_step)
    return take_step

  def classification_loss(self, classes_true, classes_logits):
    """ Class loss. If binary, two outputs"""
    entropy_fn = tf.nn.sparse_softmax_cross_entropy_with_logits

    classes_max = tf.argmax(classes_true, axis=1)
    class_loss = entropy_fn(
                      labels=classes_max,
                      logits=classes_logits)
    return class_loss

  def predict(self, labels, logits):
    """ Returns class label (int) for prediction and gold
    Args:
      pred_logits : predicted logits, not yet softmax
      classes : labels as one-hot vectors
    """
    y_prob = tf.nn.softmax(logits)
    y_pred = tf.argmax(y_prob, axis=1)
    y_true = tf.argmax(labels, axis=1)

    return y_prob, y_pred, y_true

  def get_logits(self, col_attn, row_attn):
    """ Default final layer, mean-pool RNN states, no attention """
    out = tf.reduce_mean(self.encoded_outputs, axis=1)

    in_dim = self.encoder_h_size
    # out = dense(mean, in_dim, hp.fc_units, act=tf.nn.relu, scope="h")
    out = tf.nn.dropout(out, self.keep_prob)

    # Output layer
    logits = dense(out, in_dim, hp.num_classes, act=None, scope="class_log")
    return logits

class PairWiseAttn(RNN_base):
  """ Pair-wise Attn """
  def __init__(self,params, embedding, postag_size):
    super().__init__(params, embedding, postag_size)

    # Override logits method
    self.logits = self.get_logits(self.col_attn,self.row_attn)

  def flat_concat(self, col_attn, row_attn):
    """ Reshape and concat the normalized attention """
    flat_col_dim = tf.shape(col_attn)[1]*tf.shape(col_attn)[2]
    flat_col = tf.reshape(col_attn, [-1, flat_col_dim])
    flat_row_dim = tf.shape(row_attn)[1]*tf.shape(row_attn)[2]
    flat_row = tf.reshape(row_attn, [-1, flat_row_dim])
    concat = tf.concat([flat_col, flat_row], 1)
    return concat

  def get_logits(self, col_attn, row_attn):
    """
    Simply concat the attn matrices and connect to output
    """
    self.concat = self.flat_concat(col_attn, row_attn)
    in_dim = hp.max_seq_len**2*2
    logits = dense(self.concat, in_dim, hp.num_classes, act=None, scope="class_log")
    return logits

class AttnAttn(RNN_base):
  """
  Attn over attn, based mostly on https://arxiv.org/pdf/1607.04423.pdf,
  except for final layer which is fully connected to number of classes
  """
  def __init__(self, params, embedding, postag_size, fc_layer=True):
    super().__init__(params, embedding, postag_size)

    # Override logits method
    self.logits = self.get_logits(self.col_attn,self.row_attn)

  def get_logits(self, col_attn, row_attn):
    # Get attn over attn
    self.attn_over_attn = self.attn_attn(col_attn, row_attn)

    # FC layer before output
    in_dim = hp.max_seq_len
    attnattn = dense(self.attn_over_attn, in_dim, hp.fc_units, act=tf.nn.relu, scope="h")
    attnattn = tf.nn.dropout(attnattn, self.keep_prob)

    in_dim=hp.fc_units
    # Optional fc layer
    for i in range(hp.h_layers):
      name = "dense{}".format(i)
      attnattn = dense(attnattn, in_dim, hp.fc_units,act=tf.nn.relu,scope=name)
      attnattn = tf.nn.dropout(attnattn, self.keep_prob)
      in_dim=hp.fc_units

    # Output layer
    logits = dense(attnattn, in_dim, hp.num_classes, act=None, scope="class_log")
    return logits

  def attn_attn(self, col_attn, row_attn):
    """
    Average the softmax matrices
    """
    # For the row-wise softmax tensor, we want column-wise average -> dim 1
    # This results in a vector shape [sequence len]
    col_av = tf.reduce_mean(row_attn, axis=1)

    # Attn-over-attn -> a dot product between column average vector and
    # column-wise softmax matrix. Result is a single vector [sequence len]
    # per sample
    attnattn = tf.einsum('ajk,ak->aj',col_attn,col_av)
    return attnattn

class AttnAttnSum(RNN_base):
  """
  Self-attention-over-attention for weighted sum of encoded input
  """
  def __init__(self, params, embedding, postag_size, fc_layer=True):
    super().__init__(params, embedding, postag_size)

    # Override logits method
    self.logits = self.get_sum_logits(self.col_attn,self.row_attn)

  # Override logits function
  def get_sum_logits(self, col_attn, row_attn):
    # Get attn over attn vector
    self.attn_over_attn = self.attn_attn(col_attn, row_attn)

    # Multiply the attention vector by encoded outputs (broadcast) and sum across time
    if hasattr(hp, 'parallel') and hp.parallel==False:
      self.weighted_encoded = tf.einsum('ajk,aj->ak',self.encoded_outputs,self.attn_over_attn)
    else:
      self.weighted_encoded = tf.einsum('ajk,aj->ak',self.encoded_outputs_emb,self.attn_over_attn)

    # FC layer before output
    in_dim = self.encoder_h_size
    attnattn = dense(self.weighted_encoded, in_dim, hp.fc_units, act=tf.nn.relu, scope="h_sum")
    attnattn = tf.nn.dropout(attnattn, self.keep_prob)

    in_dim=hp.fc_units
    # Optional fc layer
    for i in range(hp.h_layers):
      name = "dense_sum{}".format(i)
      attnattn = dense(attnattn, in_dim, hp.fc_units,act=tf.nn.relu,scope=name)
      attnattn = tf.nn.dropout(attnattn, self.keep_prob)
      in_dim=hp.fc_units

    # Output layer
    logits = dense(attnattn, in_dim, hp.num_classes, act=None, scope="class_log_sum")
    return logits

  def attn_attn(self, col_attn, row_attn):
    """
    Average the softmax matrices
    """
    # For the row-wise softmax tensor, we want column-wise average -> dim 1
    # This results in a vector shape [sequence len]
    col_av = tf.reduce_mean(row_attn, axis=1)

    # Attn-over-attn -> a dot product between column average vector and
    # column-wise softmax matrix. Result is a single vector [sequence len]
    # per sample
    attnattn = tf.einsum('ajk,ak->aj',col_attn,col_av)
    return attnattn

class ConvAttn(PairWiseAttn):
  """
  Given pair-wise matching score tensors, we convolve over them. Intuition
  is to detect clusters of local attention
  """
  def __init__(self, params, embedding, postag_size, fc_layer=True):
    super().__init__(params, embedding, postag_size)

  # Override logits function
  def get_logits(self, col_attn, row_attn):
    # Convolve + non-linearity
    self.col_conv = self.convolution(col_attn, scope='col_conv')
    self.row_conv = self.convolution(row_attn, scope='row_conv')

    # Pool
    self.col_pool = self.max_pool(self.col_conv, scope='col_pool')
    self.col_pool = tf.nn.dropout(self.col_pool, self.keep_prob)
    self.row_pool = self.max_pool(self.row_conv, scope='row_pool')
    self.row_pool = tf.nn.dropout(self.row_pool, self.keep_prob)

    # Flatten and concat the two
    self.final = tf.concat([self.col_pool, self.row_pool], 1)

    # Optional Hidden layers
    in_dim = hp.out_channels*2
    for i in range(hp.h_layers):
      name = "dense{}".format(i)
      self.final = dense(self.final, in_dim, hp.fc_units,act=tf.nn.relu,scope=name)
      self.final = tf.nn.dropout(self.final, self.keep_prob)
      in_dim=hp.fc_units

    # Output layer
    logits = dense(self.final, in_dim, hp.num_classes, act=None, scope="class_log")
    return logits

  def convolution(self, x, scope):
    """
    Args:
      x: a [batch_size, seq_len, seq_len] pair-wise score tensor
      scope: need a scope name, otherwise variable naming error
    Returns:
      activated tensor. If x is shape [32,60,60], kernel has h/w 2, stride 2
      and output 32, then returns tensor shape [32,29,29,32]
    """
    # Expand last dim for convolution operation
    x = tf.expand_dims(x,-1)
    with tf.variable_scope(scope):
      # Kernel of shape [filter_height, filter_width, in_channels, out_channels]
      k_shape = [hp.filt_height, hp.filt_width, 1, hp.out_channels]
      kernel = tf.get_variable("c_w", shape=k_shape, dtype=floatX)
      bias = tf.get_variable("c_b", hp.out_channels, dtype=floatX)
      conv = tf.nn.conv2d( x, kernel, hp.conv_strides, hp.padding, name="conv")

      # Batch-norm
      if hp.batch_norm == True:
        conv = tf.layers.batch_normalization(conv, training=self.mode)

      # Activation
      h = tf.nn.relu(tf.nn.bias_add(conv, bias))
    return h

class ConvAttn2(PairWiseAttn):
  """
  1D convolve rows and cols
  Given pair-wise matching score tensors, we convolve over them. Intuition
  is to detect clusters of local attention
  """
  def __init__(self, params, embedding, postag_size, fc_layer=True):
    super().__init__(params, embedding, postag_size)

  # Override logits function
  def get_logits(self, col_attn, row_attn):
    # Convolve col attn matrix as 1D over columns
    # Kernel of shape [filter_height, filter_width, in_channels, out_channels]
    # Col
    k_shape = [hp.max_seq_len, 1, 1, 1]
    self.col_conv = self.convolution(col_attn, k_shape, scope='col_conv')
    self.col_conv = tf.nn.dropout(self.col_conv, self.keep_prob)
    self.col_conv = tf.squeeze(self.col_conv, [1,3])
    # Row
    k_shape = [1, hp.max_seq_len, 1, 1]
    self.row_conv = self.convolution(row_attn, k_shape, scope='row_conv')
    self.row_conv = tf.nn.dropout(self.row_conv, self.keep_prob)
    self.row_conv = tf.squeeze(self.row_conv, [2,3])

    # Flatten and concat the two
    self.final = tf.concat([self.col_conv, self.row_conv], 1)

    # Optional Hidden layers
    in_dim = hp.max_seq_len*2
    in_dim = self.final.get_shape()[1]
    for i in range(hp.h_layers):
      name = "dense{}".format(i)
      self.final = dense(self.final, in_dim, hp.fc_units,act=tf.nn.relu,scope=name)
      self.final = tf.nn.dropout(self.final, self.keep_prob)
      in_dim=hp.fc_units

    # Output layer
    logits = dense(self.final, in_dim, hp.num_classes, act=None, scope="class_log")
    return logits

  def convolution(self, x, k_shape, scope):
    """
    Args:
      x: a [batch_size, seq_len, seq_len] pair-wise score tensor
      scope: need a scope name, otherwise variable naming error
    Returns:
      activated tensor. If x is shape [32,60,60], kernel has h/w 2, stride 2
      and output 32, then returns tensor shape [32,29,29,32]
    """
    # Expand last dim for convolution operation
    x = tf.expand_dims(x,-1)
    with tf.variable_scope(scope):
      kernel = tf.get_variable("c_w", shape=k_shape, dtype=floatX)
      bias = tf.get_variable("c_b", k_shape[-1], dtype=floatX)
      conv = tf.nn.conv2d( x, kernel, hp.conv_strides, hp.padding, name="conv")

      # Batch-norm
      if hp.batch_norm == True:
        conv = tf.layers.batch_normalization(conv, training=self.mode)

      # Activation
      h = tf.nn.relu(tf.nn.bias_add(conv, bias))
    return h

  def max_pool(self, x, scope):
    """
    If say input is shape [32,29,29,32], pool shape is [1,29,29,1] with stride 1,
    then output is [32, 32]
    """
    with tf.variable_scope(scope):
      p_shape = [1, 29, 29, 1]
      stride = [1,1,1,1]
      pooled = tf.nn.max_pool(
          x,
          p_shape,
          stride,
          hp.padding,
          data_format='NHWC')
      pooled = tf.squeeze(pooled, [1,2]) # squeeze single elem dimensions
      return pooled
  def max_pool(self, x, scope):
    """
    If say input is shape [32,29,29,32], pool shape is [1,29,29,1] with stride 1,
    then output is [32, 32]
    """
    with tf.variable_scope(scope):
      p_shape = [1, 29, 29, 1]
      stride = [1,1,1,1]
      pooled = tf.nn.max_pool(
          x,
          p_shape,
          stride,
          hp.padding,
          data_format='NHWC')
      pooled = tf.squeeze(pooled, [1,2]) # squeeze single elem dimensions
      return pooled

def dense(x, in_dim, out_dim, scope, act=None):
  """ Fully connected layer builder"""
  with tf.variable_scope(scope):
    weights = tf.get_variable("weights", shape=[in_dim, out_dim],
              dtype=floatX, initializer=tf.orthogonal_initializer())
    biases = tf.get_variable("biases", out_dim,
              dtype=floatX, initializer=tf.constant_initializer(0.0))
    # Pre activation
    h = tf.matmul(x,weights) + biases
    # Post activation
    if act:
      h = act(h)
    return h

