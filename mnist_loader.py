__author__ = 'joschlemper'

import cPickle
import gzip
import os
import sys
import time
from sklearn import preprocessing
import numpy as np
import theano
import theano.tensor as T

try:
    import PIL.Image as Image
except ImportError:
    import Image

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, 'data')


def load_digits(shared=True, digits=None, pre=None, n=None):
    '''
    :param shared: To return theano shared variable. If false, returns in numpy
    :param digits: filter. if none, all digits will be returned
    :param pre: a dictionary of preprocessing. Options: pca, white-pca, center, threshold
    :param n: (a single digit or) an array showing how many samples to get
    :return: [(train_x, train_y), (valid_x, valid_y), (test_x, test_y)]
    '''
    data = __load()

    # pre-processing
    if digits:
        new_data = []
        for data_xy in data:
            data_y = data_xy[1]
            filtered = filter(lambda (x, y): y in digits, enumerate(data_y))
            idx = [s[0] for s in filtered]
            new_data.append((data_xy[0][idx], data_xy[1][idx]))
        data = new_data

    if n:
        new_data = []
        for i, data_xy in enumerate(data):
            idx = np.random.randint(0, len(data_xy[1]), size=n[i])
            new_data.append((data_xy[0][idx], data_xy[1][idx]))
        data = new_data

    if pre:
        if 'pca' in pre:
            pass
        if 'wpca' in pre:
            pass
        if 'scale' in pre:
            new_data = []
            for i, data_xy in enumerate(data):
                if len(data_xy[0] > 0):
                    data_x = preprocessing.scale(data_xy[0])
                else:
                    data_x = data_xy[0]
                new_data.append((data_x, data_xy[1]))
            data = new_data
        if 'center' in pre:
            pass
        if 'threshold' in pre:
            data = get_binary(data, pre['threshold'])
        if 'binary_label' in pre:
            data = get_binary_label(data)
        if 'label_vector' in pre:
            data = vectorise_label(data)

    if shared:
        data = get_shared(data)

    return data

def __load():
    ''' Loads the mnist data set '''
    dataset_name = 'mnist.pkl.gz'

    # look for the location
    possible_locations = ['', '/data/']

    dataset = DATA_DIR
    for location in possible_locations:
        data_location = os.path.join(BASE_DIR, location, dataset_name)
        if os.path.isfile(data_location):
            dataset = data_location

    # Download the MNIST dataset if it is not present
    if not os.path.isfile(dataset):
        import urllib
        origin = ('http://www.iro.umontreal.ca/~lisa/deep/data/mnist/mnist.pkl.gz')
        print '... downloading data from %s' % origin
        urllib.urlretrieve(origin, dataset)

    print '... loading data'

    # Load the dataset
    f = gzip.open(dataset, 'rb')
    train_set, valid_set, test_set = cPickle.load(f)
    f.close()

    return train_set, valid_set, test_set


def shared_dataset(data_xy, borrow=True):
    """ Function that loads the dataset into shared variables

    The reason we store our dataset in shared variables is to allow
    Theano to copy it into the GPU memory (when code is run on GPU).
    Since copying data into the GPU is slow, copying a minibatch every time
    is needed (the default behaviour if the data is not in a shared
    variable) would lead to a large decrease in performance.
    """
    data_x, data_y = data_xy
    shared_x = theano.shared(np.asarray(data_x, dtype=theano.config.floatX), borrow=borrow)
    shared_y = theano.shared(np.asarray(data_y, dtype=theano.config.floatX), borrow=borrow)
    # When storing data on the GPU it has to be stored as floats
    # therefore we will store the labels as ``floatX`` as well
    # (``shared_y`` does exactly that). But during our computations
    # we need them as ints (we use labels as index, and if they are
    # floats it doesn't make sense) therefore instead of returning
    # ``shared_y`` we will have to cast it to int. This little hack
    # lets ous get around this issue
    return shared_x, T.cast(shared_y, 'int32')


def get_shared(data):
    train_set, valid_set, test_set = data
    train_set_x, train_set_y = shared_dataset(train_set)
    valid_set_x, valid_set_y = shared_dataset(valid_set)
    test_set_x, test_set_y = shared_dataset(test_set)
    return [(train_set_x, train_set_y), (valid_set_x, valid_set_y), (test_set_x, test_set_y)]


def get_binary(data, t=0.5):
    # Preprocessing
    new_data = []
    for data_xy in data:
        new_data.append((to_binary(data_xy[0]), data_xy[1]))
    return new_data


def to_binary(data, t=0.5):
    """
    :param data: 2 dimensional np array
    :param t: threshold value
    :return: data with binary data, 1 if data[i] > t, 0 otherwise
    """
    data[data >= t] = 1
    data[data < t] = 0
    return data


def scale_to_unit_interval(ndar, eps=1e-8):
    """ Scales all values in the ndarray ndar to be between 0 and 1 """
    ndar = ndar.copy()
    ndar -= ndar.min()
    ndar *= 1.0 / (ndar.max() + eps)
    return ndar


def get_binary_label(data):
    new_data = []
    for (x, y) in data:
        new_data.append((x, (y % 2)))
    return new_data


def get_target_vector(x):
    xs = np.zeros(10, dtype=theano.config.floatX)
    xs[x] = 1
    return xs


def sample_image(data, shared=True):
    # convert to numpy first
    if 'Tensor' in str(type(data)):
        seq = data.eval()
    else:
        seq = data

    digits = np.unique(seq).tolist()
    image_pool = {}
    for d in digits:
        train, _, _ = load_digits(shared=False, digits=[d], n=[len(seq), 0, 0])
        image_pool[d] = train[0]

    sample_data = []
    rand_seq = np.random.randint(0, len(seq), size=len(seq))

    for d, r in zip(seq.tolist(), rand_seq.tolist()):
        sample_data.append(image_pool[d][(r % len(image_pool[d]))])

    if shared:
        return theano.shared(np.asarray(sample_data, dtype=theano.config.floatX), borrow=True)
    else:
        return np.asarray(sample_data, dtype=theano.config.floatX)


def vectorise_label(data):
    new_data = []
    for (x, y) in data:
        new_data.append((x, np.array(map(get_target_vector, y))))
    return new_data


def load_shared():
    train_set, valid_set, test_set = __load()

    # Convert to theano shared variables
    train_set_x, train_set_y = shared_dataset(train_set)
    valid_set_x, valid_set_y = shared_dataset(valid_set)
    test_set_x, test_set_y = shared_dataset(test_set)

    rval = [(train_set_x, train_set_y), (valid_set_x, valid_set_y),
            (test_set_x, test_set_y)]
    return rval


def load_data_threshold(dataset, t=0.5):
    [(train_set_x, train_set_y), (valid_set_x, valid_set_y),
            (test_set_x, test_set_y)] = __load()
    new_train_x = to_binary(train_set_x, t)
    new_valid_x = to_binary(valid_set_x, t)
    new_test_x = to_binary(test_set_x, t)

    return [(new_train_x, train_set_y), (new_valid_x, valid_set_y),
            (new_test_x, test_set_y)]


def save_digits(x, image_name='digits.png'):
    data_size = x.shape[0]
    image_data = np.zeros((29, 29 * data_size - 1), dtype='uint8')

    image_data[0:28, :] = tile_raster_images(
        X=x,
        img_shape=(28, 28),
        tile_shape=(1, data_size),
        tile_spacing=(1, 1)
    )

    # construct image
    image = Image.fromarray(image_data)
    image.save(image_name)


def save_digit(x, name="digit.png"):
    image_data = np.zeros((29, 29), dtype='uint8')

    # Original images
    image_data = tile_raster_images(
        X=np.array([x]),
        img_shape=(28, 28),
        tile_shape=(1, 1),
        tile_spacing=(1, 1)
    )

    image = Image.fromarray(image_data)
    image.save(name)


def tile_raster_images(X, img_shape, tile_shape, tile_spacing=(0, 0),
                       scale_rows_to_unit_interval=True,
                       output_pixel_vals=True):
    """
    Transform an array with one flattened image per row, into an array in
    which images are reshaped and layed out like tiles on a floor.

    This function is useful for visualizing datasets whose rows are images,
    and also columns of matrices for transforming those rows
    (such as the first layer of a neural net).

    :type X: a 2-D ndarray or a tuple of 4 channels, elements of which can
    be 2-D ndarrays or None;
    :param X: a 2-D array in which every row is a flattened image.

    :type img_shape: tuple; (height, width)
    :param img_shape: the original shape of each image

    :type tile_shape: tuple; (rows, cols)
    :param tile_shape: the number of images to tile (rows, cols)

    :param output_pixel_vals: if output should be pixel values (i.e. int8
    values) or floats

    :param scale_rows_to_unit_interval: if the values need to be scaled before
    being plotted to [0,1] or not


    :returns: array suitable for viewing as an image.
    (See:`Image.fromarray`.)
    :rtype: a 2-d array with same dtype as X.

    """

    assert len(img_shape) == 2
    assert len(tile_shape) == 2
    assert len(tile_spacing) == 2

    # The expression below can be re-written in a more C style as
    # follows :
    #
    # out_shape    = [0,0]
    # out_shape[0] = (img_shape[0]+tile_spacing[0])*tile_shape[0] -
    #                tile_spacing[0]
    # out_shape[1] = (img_shape[1]+tile_spacing[1])*tile_shape[1] -
    #                tile_spacing[1]
    out_shape = [
        (ishp + tsp) * tshp - tsp
        for ishp, tshp, tsp in zip(img_shape, tile_shape, tile_spacing)
    ]

    if isinstance(X, tuple):
        assert len(X) == 4
        # Create an output np ndarray to store the image
        if output_pixel_vals:
            out_array = np.zeros((out_shape[0], out_shape[1], 4),
                                    dtype='uint8')
        else:
            out_array = np.zeros((out_shape[0], out_shape[1], 4),
                                    dtype=X.dtype)

        #colors default to 0, alpha defaults to 1 (opaque)
        if output_pixel_vals:
            channel_defaults = [0, 0, 0, 255]
        else:
            channel_defaults = [0., 0., 0., 1.]

        for i in xrange(4):
            if X[i] is None:
                # if channel is None, fill it with zeros of the correct
                # dtype
                dt = out_array.dtype
                if output_pixel_vals:
                    dt = 'uint8'
                out_array[:, :, i] = np.zeros(
                    out_shape,
                    dtype=dt
                ) + channel_defaults[i]
            else:
                # use a recurrent call to compute the channel and store it
                # in the output
                out_array[:, :, i] = tile_raster_images(
                    X[i], img_shape, tile_shape, tile_spacing,
                    scale_rows_to_unit_interval, output_pixel_vals)
        return out_array

    else:
        # if we are dealing with only one channel
        H, W = img_shape
        Hs, Ws = tile_spacing

        # generate a matrix to store the output
        dt = X.dtype
        if output_pixel_vals:
            dt = 'uint8'
        out_array = np.zeros(out_shape, dtype=dt)

        for tile_row in xrange(tile_shape[0]):
            for tile_col in xrange(tile_shape[1]):
                if tile_row * tile_shape[1] + tile_col < X.shape[0]:
                    this_x = X[tile_row * tile_shape[1] + tile_col]
                    if scale_rows_to_unit_interval:
                        # if we should scale values to be between 0 and 1
                        # do this by calling the `scale_to_unit_interval`
                        # function
                        this_img = scale_to_unit_interval(
                            this_x.reshape(img_shape))
                    else:
                        this_img = this_x.reshape(img_shape)
                    # add the slice to the corresponding position in the
                    # output array
                    c = 1
                    if output_pixel_vals:
                        c = 255
                    out_array[
                        tile_row * (H + Hs): tile_row * (H + Hs) + H,
                        tile_col * (W + Ws): tile_col * (W + Ws) + W
                    ] = this_img * c
        return out_array

def construct_atlas():
    '''
    :return: statistical mean image of digits from 0 to 9
    '''
    dataset = load_digits(shared=False)
    tr, vl, te = dataset
    tr_x, tr_y = tr

    d_img_arrays = {}
    for i in xrange(0,10):
        d_img_arrays[i] = []

    for x, y in zip(tr_x, tr_y):
        d_img_arrays[y].append(x)

    for k in d_img_arrays:
        d_img_arrays[k] = np.mean(d_img_arrays[k],axis=0)

    d_img_arrays[len(d_img_arrays)+1] = np.mean(d_img_arrays.values(), axis=0)

    return d_img_arrays

if __name__ == '__main__':
    atlas = construct_atlas()
    for k in atlas:
        save_digit(atlas[k], "atlas/digit_%d.png" % k)
