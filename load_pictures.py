import imageio
import os
from os import listdir
import numpy as np
from skimage.transform import resize

def txt_to_array(path):
    with open(path) as file:
        return [[float(word.strip()) for word in line.split(' ')] for line in file]

def load_pictures(basedir='./data/', downsample=8, render_poses = []):
    # render_poses = ['2_test_0000','2_test_0016','2_test_0055','2_test_0093','2_test_0160']
    # loading images
    imgs_dir = os.path.join(basedir, 'rgb')
    poses_dir = os.path.join(basedir, 'pose')
    # getting all poses and images
    all_poses_fnames = [os.path.join(poses_dir,f) for f in sorted(listdir(poses_dir)) if f[0]!='.']
    all_imgs_fnames = [os.path.join(imgs_dir,f) for f in sorted(listdir(imgs_dir)) if f[0]!='.']
    
    train_poses = sorted([fname for fname in all_poses_fnames if 'train' in fname])
    val_poses = sorted([fname for fname in all_poses_fnames if 'val' in fname])
    test_poses = sorted([fname for fname in all_poses_fnames if 'test' in fname])
    
    if render_poses is not None:
        render_poses = sorted([fname for fname in all_poses_fnames if any([filter in fname for filter in render_poses])])
    else:
        render_poses = test_poses

    train_imgs = sorted([fname for fname in all_imgs_fnames if 'train' in fname])
    val_imgs = sorted([fname for fname in all_imgs_fnames if 'val' in fname])
    test_imgs = sorted([fname for fname in all_imgs_fnames if 'test' in fname])
    # no test images results in a None entry
    if len(test_imgs) < len(test_poses):
        len_diff = len(test_poses) - len(test_imgs)
        test_imgs += [None] * len_diff
    # 
    all_imgs = train_imgs + val_imgs + test_imgs
    all_poses = train_poses + val_poses + test_poses
    counts = [0, len(train_poses),len(all_poses)]
    i_split = [np.arange(counts1, counts2) for counts1, counts2 in zip(counts,counts[1:])]
    
    imgs = [] 
    last_valid_index_shape = 0
    for fname in all_imgs:
        if fname is not None: 
            img = imageio.imread(fname)/255
            img = resize(img, (img.shape[0]//downsample,img.shape[1]//downsample))
            last_valid_index_shape = img.shape
        else:
            img = np.empty(last_valid_index_shape)
        imgs.append(img)
        
    imgs = np.asarray(imgs).astype(np.float32)

    poses = np.asarray(
        [txt_to_array(fname)  
        for fname in all_poses]
        ).astype(np.float32)
    
    H, W = imgs[0].shape[:2]

    int_dir = os.path.join(basedir, 'intrinsics.txt')
    intrinsic = np.asarray(txt_to_array(int_dir))
    focal = intrinsic[0,0]
        
    return imgs, poses, render_poses, [H, W, focal], i_split
