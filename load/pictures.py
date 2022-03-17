
from os import listdir
from os.path import join

import numpy as np
from cv2 import resize
from imageio import imread


def txt_to_array(path):
    with open(path) as file:
        return [[float(word.strip()) for word in line.split(' ')] for line in file]

def load_pictures(args):
    basedir = args.datadir
    downsample = args.render_factor

    # loading images
    imgs_dir = join(basedir, 'rgb')
    poses_dir = join(basedir, 'pose')
    # getting all poses and images
    all_poses_fnames = [join(poses_dir,f) for f in sorted(listdir(poses_dir)) if f[0]!='.']
    all_imgs_fnames = [join(imgs_dir,f) for f in sorted(listdir(imgs_dir)) if f[0]!='.']
    
    train_poses = sorted([fname for fname in all_poses_fnames if 'train' in fname])
    val_poses = sorted([fname for fname in all_poses_fnames if 'val' in fname])
    test_poses = sorted([fname for fname in all_poses_fnames if 'test' in fname])
    
    render_poses = test_poses
    render_poses = np.asarray(render_poses)

    train_imgs = sorted([fname for fname in all_imgs_fnames if 'train' in fname])
    val_imgs = sorted([fname for fname in all_imgs_fnames if 'val' in fname])
    test_imgs = sorted([fname for fname in all_imgs_fnames if 'test' in fname])
    # no test images results in a None entry
    if len(test_imgs) < len(test_poses):
        len_diff = len(test_poses) - len(test_imgs)
        test_imgs += [None] * len_diff
    
    all_imgs = train_imgs + val_imgs + test_imgs
    all_poses = train_poses + val_poses + test_poses
    counts = [0, len(train_poses),len(train_poses)+len(val_poses),len(all_poses)]
    i_split = [np.arange(counts1, counts2) for counts1, counts2 in zip(counts,counts[1:])]
    
    imgs = [] 
    for fname in all_imgs:
        if fname is not None: 
            img = imread(fname)/255
            img = resize(img, (img.shape[0]//downsample,img.shape[1]//downsample))
        else: raise ValueError('No image found for pose {}'.format(fname))
        imgs.append(img)
        
    imgs = np.asarray(imgs).astype(np.float32)

    poses = []
    for fname in all_poses:
        pose = np.asarray(txt_to_array(fname))
        pose[:, 1:3] *= -1
        poses.append(pose.tolist())

    poses = np.asarray(poses).astype(np.float32)
    
    H, W = imgs[0].shape[:2]

    int_path = join(basedir, 'intrinsics.txt')
    K = np.asarray(txt_to_array(int_path))
    focal = K[0,0]

    # near anf far calculations
    bbox_path = join(basedir, 'bbox.txt')
    bounds = np.asarray(txt_to_array(bbox_path)[0])
    min_corner, max_corner = bounds[:3],bounds[3:-1]
    trans = poses[...,:3,-1]
    camera_radius = np.max(np.diag(trans @ trans.T)**.5)
    largest_obj_rad = np.max([np.linalg.norm(min_corner),np.linalg.norm(max_corner)])    

    near = np.floor(camera_radius - largest_obj_rad) - 1
    far = np.ceil(camera_radius + largest_obj_rad) + 1

    # recommended by piazza
    # near = 1.
    # far = 5.
    # actual 0. , 6.
    
    return imgs, poses, render_poses, [H, W, focal], K, i_split, near, far
