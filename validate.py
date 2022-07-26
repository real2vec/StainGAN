import time
import os, sys
from options.test_options import TestOptions
from data.data_loader import CreateDataLoader
from models.models import create_model

from PIL import Image
from torch import nn
import torch
from data.base_dataset import get_transform
import torchvision

opt = TestOptions().parse()
opt.nThreads = 1  # test code only supports nThreads = 1
opt.batchSize = 1  # test code only supports batchSize = 1
opt.serial_batches = True  # no shuffle
opt.no_flip = True  # no flip

# data_loader = CreateDataLoader(opt)
# dataset = data_loader.load_data()
transforms = get_transform(opt)
# img_paths = [
#     "/data/shared/her2-images/test-set-external/400-1.jpg",
#     "/data/shared/her2-images/test-set-external/96-3.jpg",
#     "/data/shared/her2-images/test-set-external/101-3.jpg",
#     "/data/shared/her2-images/test-set-external/58-1.jpg",
#     "/data/shared/her2-images/test-set-external/133-3.jpg",
#     "/data/shared/her2-images/test-set-external/136-2.jpg",
#     "/data/shared/her2-images/test-set-external/136-3.jpg",
#     "/data/shared/her2-images/test-set-external/212-3.jpg",
#     "/data/shared/her2-images/test-set-external/425-1.jpg",
#     "/data/shared/her2-images/test-set-external/425-2.jpg",
#     "/data/shared/her2-images/test-set-external/273-1.jpg",
#     "/data/shared/her2-images/test-set-external/65-1.jpg",
#     "/data/shared/her2-images/test-set-external/68-1.jpg",
#     "/data/shared/her2-images/test-set-external/108-2.jpg",
#     "/data/shared/her2-images/test-set-external/108-1.jpg",
#     "/data/shared/her2-images/test-set-external/99-1.jpg",
# ]

BASE_PATH = "/data/shared/her2-images/test-set-external"
img_paths = [os.path.join(BASE_PATH, f) for f in os.listdir(BASE_PATH) if os.path.isfile(os.path.join(BASE_PATH, f))]

# test
start_time = time.time()
TARGET_SIZE = 256
STRIDE_SIZE = TARGET_SIZE // 2
model = create_model(opt)

RESULT_VERSION = "full-v1"
RESULT_PATH = os.path.join("result", RESULT_VERSION)
if not os.path.exists(RESULT_PATH):
        os.makedirs(RESULT_PATH)

def remove_odd_shape(img):
    n_img = img 
    if n_img.shape[-1] % 2 == 1:
        n_img = n_img[:, :, :, 1:]

    if n_img.shape[-2] % 2 == 1:
        n_img = n_img[:, :, 1:, :]
    return n_img

def _get_padding(value):
    aux = STRIDE_SIZE - value 
    aux %= STRIDE_SIZE
    aux //= 2

    return aux

def get_padding(img):
    fst = _get_padding(img.shape[-2])
    snd = _get_padding(img.shape[-1])

    return (fst, snd)

def pass_tensor(model, tensor):
    tensor = tensor.to(torch.cuda.current_device())
    fake, cycle = model.forward_direct(tensor)

    fake = fake.cpu()
    cycle = cycle.cpu()

    return fake, cycle

for path in img_paths:
    print(path)
    img = Image.open(path).convert('RGB')
    # img = torchvision.transforms.ToTensor()(img).unsqueeze(0)
    img = transforms(img).unsqueeze(0)
    img = remove_odd_shape(img)
    padding = get_padding(img)
    
    new_path = os.path.join(RESULT_PATH, path.split("/")[-1])
    if not os.path.exists(new_path):
        os.makedirs(new_path)
    torchvision.utils.save_image(img, os.path.join(new_path, "normalized.jpg"))

    fold_params = dict(kernel_size=TARGET_SIZE, stride=STRIDE_SIZE, padding=padding)
    unfold = nn.Unfold(**fold_params)
    fold = nn.Fold(img.shape[2:], **fold_params)

    divisor = fold(unfold(torch.ones_like(img)))
    unfolded_img = unfold(img)
    unfolded_img_shape = unfolded_img.shape
    unfolded_img = unfolded_img.view(3, TARGET_SIZE, TARGET_SIZE, -1)
    unfolded_img = torch.permute(unfolded_img, (3,0,1,2))

    pairs = [pass_tensor(model, tensor) for tensor in torch.split(unfolded_img, 32, dim=0)]

    fake = [pair[0] for pair in pairs]
    cycle = [pair[1] for pair in pairs]

    fake = torch.cat(fake, dim=0)
    cycle = torch.cat(cycle, dim=0)

    fake = torch.permute(fake, (1,2,3,0))
    cycle = torch.permute(cycle, (1,2,3,0))

    fake = fake.view(unfolded_img_shape)
    cycle = cycle.view(unfolded_img_shape)

    fake = fold(fake) 
    cycle = fold(cycle)

    fake = fake / divisor
    cycle = cycle / divisor

    torchvision.utils.save_image(fake, os.path.join(new_path, "fake.jpg"))
    torchvision.utils.save_image(cycle, os.path.join(new_path, "cycle.jpg"))

elapsed = (time.time() - start_time)
print("--- %s seconds ---" % round((elapsed ), 2))
