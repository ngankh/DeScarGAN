# Copyright 2020 University of Basel, Center for medical Image Analysis and Navigation
#
# Licensed under the Apache License, Version 2.0 (the “License”);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an “AS IS” BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import torch
from sklearn.metrics import confusion_matrix
import torchvision
import torchvision.transforms as transforms
from visdom import Visdom
import matplotlib.pyplot as plt
import PIL.Image
import torchvision.transforms.functional as TF
from scipy import misc
import os
import math
import numpy as np
import scipy.ndimage.morphology
import torch.nn as nn
import random
import torch.optim as optim

vis=Visdom()

def read_mha_to_numpy(file_path):
    itk_image = itk.imread(file_path)
    image = np.copy(itk.GetArrayViewFromImage(itk_image))
    size = image.shape
    return image

def npy_loader(path):
    sample = torch.from_numpy(np.load(path))
    return sample


def standardize(img):
    mean = np.mean(img)
    std = np.std(img)
    img = (img - mean) / std
    return img




def kappa_score(preds1, preds2):
    cnf = confusion_matrix(preds1, preds2)
    row_marg = np.sum(cnf, axis=1)
    col_marg = np.sum(cnf, axis=0)
    marg_mult = col_marg * row_marg
    n = np.sum(row_marg)
    pr_e = np.sum(marg_mult) / n / n
    pr_a = (cnf[0][0] + cnf[1][1]) / n
    kappa = (pr_a - pr_e) / (1 - pr_e)

    se_k = (pr_a * (1 - pr_a)) / (n * (1 - pr_e) ** 2)
    lower = kappa - 1.96 * se_k
    upper = kappa + 1.96 * se_k
    return kappa, lower, upper


def normalize(img):

    _min = img.min()
    _max = img.max()
    normalized_img = 2*(img - _min) / (_max - _min)-1
    return normalized_img


def visualize(img):
    _min = img.min()
    _max = img.max()
    normalized_img = (img - _min)/ (_max - _min)
    return normalized_img



def imshow(npimg):
    npimg = npimg / 2 + 0.5     # unnormalize
    npimg = npimg.detach().numpy()
    plt.imshow(np.transpose(npimg, (1, 2, 0)))
    plt.show()


class TransposeNumpy:
    """Transposes a numpy.ndarray

    Can be used just like torchvision.transforms
    """
    def __init__(self, transposition):
        self.transposition = transposition


    def __call__(self, numpyArray):
        outArray = numpyArray.transpose(self.transposition)
        return outArray


    def __repr__(self):
        return "TransposeNumpy.__repr__() not implemented"
        pass


class MapTransformOverNumpyArrayChannels:
    """Maps a torchvision.transforms transform over the dimension 0 of a numpy.ndarray

    Takes a numpy C x H x W array and converts each channel to a PIL.Image. Applies
    the transform to each PIL.Image and converts them back to numpy  H x W x C

    Can be used just like torchvision.transforms
    """
    def __init__(self, transform):
        self.transform = transform


    def __call__(self, numpyArray):


        rng_state = random.getstate() #resetting the RNG for each layer
        np_rng_state = np.random.get_state()
        outArray = np.empty_like(numpyArray)
     
        for k, channel in enumerate(numpyArray):

            random.setstate(rng_state)
            np.random.set_state(np_rng_state)
            channel=np.array(channel)
            img = PIL.Image.fromarray(channel)
            img = self.transform(img)
            outChannel = np.array(img)
            outArray[k,:,:] = outChannel

        return outArray


    def __repr__(self):
        return "MapTransformOverNumpyArrayChannels.__repr__() not implemented"
        pass

class RandomWarpDeformer:


    def __init__(self, grid=(8, 8),  amount=0.3):
        """Grid specifies the number of quads thatt are individually transformed
        in each direction.
        """
        self.grid = grid
        self.type = type
        self.u = None
        self.v = None
        self.amount = amount
        self.nodex = np.array([[1, 1], [2, 2]]) / 3
        self.nodey = np.array([[1, 2], [2, 1]]) / 3
        self.p = lambda t: 27.0 / 2.0 * t * (t - 2 / 3) * (t - 1) #langrange interpolation poly

    def getmesh(self, img):

        (w, h) = img.size
        (n, m) = self.grid
        step = (w / n, h / m)

        self.u = 2 / 3 * self.amount * (np.random.random((2, 2)) - 0.5)
        self.v = 2 / 3 * self.amount * (np.random.random((2, 2)) - 0.5)

        def deform(x, y):
            x = x / w
            y = y / h
            px = [self.p(x), self.p(1 - x)]
            py = [self.p(y), self.p(1 - y)]
      
            dx = self.u[0,0] * px[0] * py[0] + self.u[0,1] * px[0] * py[1] + self.u[1,1] * px[1] * py[1] + self.u[1,0] * px[1] * py[0]
            dy = self.v[0,0] * px[0] * py[0] + self.v[0,1] * px[0] * py[1] + self.v[1,1] * px[1] * py[1] + self.v[1,0] * px[1] * py[0]
            regularization = 4 * x * (1 - x) * 4 * y * (1 - y)
            xreg = x + dx * regularization
            yreg = y + dy * regularization
            return int(xreg * w) , int(yreg * h)

        #generate mesh
        mesh = []
        for i in range(n):
            for j in range(m):
                x_min = int(i * step[0])
                x_max = int((i + 1) * step[0])
                y_min = int(j * step[1])
                y_max = int((j + 1) * step[1])
                target =  (x_min, y_min, x_max, y_max)
                source = (  *deform(x_min, y_min),
                            *deform(x_min, y_max),
                            *deform(x_max, y_max),
                            *deform(x_max, y_min))
                mesh.append((target, source))
        return mesh


    
    
class RandomWarpTransform():
    """Transforms an image by warping it smoothly.

    The transform is defined by moving four points within the image by a random amount. The displacement of the
    intermediate points is interpolated using polynomial interpolation. The displacement vanishes at the boundary
    of the image.

    Can be used just like torchvision.transforms
    """

    def __init__(self):
        self.rwd = RandomWarpDeformer()

    def __call__(self, img):
        """Takes PIL Image and performs random warp.
        """
        C = np.array(img)
        print('C=',C.shape)
        img2 = PIL.ImageOps.deform(img, self.rwd,  resample=PIL.Image.BILINEAR)
        return img2

    def __repr__(self):
        return "TransposeRandomWarpTransform.__repr__() not implemented"



def eval_binary_classifier(ground_truth, prediction):
    eps = 1e-10
    axis = (0, 1)
    gt_mask = ground_truth > 0
    pred_mask = prediction > 0
    tp = np.logical_and(gt_mask, pred_mask).sum(axis=axis)
    tn = np.logical_and(~gt_mask, ~pred_mask).sum(axis=axis)
    fp = np.logical_and(~gt_mask, pred_mask).sum(axis=axis)
    fn = np.logical_and(gt_mask, ~pred_mask).sum(axis=axis)
    N = tp + tn + fp + fn
    DSC = 2 * tp / (2 * tp + fp + fn + eps)
    JACC = DSC / (2 - DSC)
    ACC = (tp + tn) / N
    TPR = tp / (tp + fn + eps)  # recall
    PPV = tp / (tp + fp + eps)  # precision
    output = dict(tp=tp, tn=tn, fp=fp, fn=fn, DSC=DSC, JACC=JACC, ACC=ACC, TPR=TPR, PPV=PPV)
    output_avg = {v : k.mean() for v,k in output.items()}
    return output, output_avg



class GaussianSmoothing(nn.Module):

            def __init__(self, channels, kernel_size, sigma, dim=2):
                super(GaussianSmoothing, self).__init__()
                if isinstance(kernel_size, numbers.Number):
                    kernel_size = [kernel_size] * dim
                if isinstance(sigma, numbers.Number):
                    sigma = [sigma] * dim

                # The gaussian kernel is the product of the
                # gaussian function of each dimension.
                kernel = 1
                meshgrids = torch.meshgrid(
                    [
                        torch.arange(size, dtype=torch.float32)
                        for size in kernel_size
                    ]
                )
                for size, std, mgrid in zip(kernel_size, sigma, meshgrids):
                    mean = (size - 1) / 2
                    kernel *= 1 / (std * math.sqrt(2 * math.pi)) * \
                              torch.exp(-((mgrid - mean) / std) ** 2 / 2)

                # Make sure sum of values in gaussian kernel equals 1.
                kernel = kernel / torch.sum(kernel)

                # Reshape to depthwise convolutional weight
                kernel = kernel.view(1, 1, *kernel.size())
                kernel = kernel.repeat(channels, *[1] * (kernel.dim() - 1))

                self.register_buffer('weight', kernel)
                self.groups = channels

                if dim == 1:
                    self.conv = F.conv1d
                elif dim == 2:
                    self.conv = F.conv2d
                elif dim == 3:
                    self.conv = F.conv3d
                else:
                    raise RuntimeError(
                        'Only 1, 2 and 3 dimensions are supported. Received {}.'.format(dim)
                    )

            def forward(self, input):
                """
                Apply gaussian filter to input.
                Arguments:
                    input (torch.Tensor): Input to apply gaussian filter on.
                Returns:
                    filtered (torch.Tensor): Filtered output.
                """
                return self.conv(input, weight=self.weight, padding=1, groups=self.groups)
