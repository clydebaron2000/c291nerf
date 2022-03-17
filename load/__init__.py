import numpy as np

from .blender import load_blender_data
from .deepvoxels import load_dv_data
from .LINEMOD import load_LINEMOD_data
from .llff import load_llff_data
from .pictures import load_pictures


def load_data_from_args(args):
    data_type = args.dataset_type
    output = None
    if data_type == 'llff':
        output = load_llff_data(args)
    elif data_type == 'blender':
        output = load_blender_data(args)
    elif data_type == 'LINEMOD':
        output = load_LINEMOD_data(args)
    elif data_type == 'deepvoxels':
        output = load_dv_data(args)
    elif data_type == 'pictures':
        output = load_pictures(args)
    else:
        raise ValueError('Unknown data type: {}'.format(data_type))
    # unpacking
    images, poses, render_poses, hwf, K, i_split, near, far = output
    _, _, i_test = i_split
    H, W, focal = hwf
    H, W = int(H), int(W)
    hwf = [H, W, focal]
    print('near far', near, far)
    if K is None:
        K = np.array([
            [focal, 0, 0.5*W],
            [0, focal, 0.5*H],
            [0, 0, 1]
        ])
    if args.render_test:
        print("Rendering test poses")
        render_poses = np.array(poses[i_test])

    print(f'Loaded {data_type}', images.shape, render_poses.shape, hwf, args.datadir)

    if args.white_bkgd:
        print("Adding white background")
        images = images[...,:3]*images[...,-1:] + (1.-images[...,-1:])
    else:
        images = images[...,:3]
        
    return images, poses, render_poses, hwf, K, i_split, near, far
