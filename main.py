from datetime import datetime as date
import json, random, sys, time
from os import listdir, makedirs, mkdir
from os.path import join as path_join

import imageio
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch.nn.functional import relu as relu_func
from tqdm import tqdm, trange
import wandb

from load import load_data_from_args
from utils.nerf_helpers import *

from utils.parser import config_parser

np.random.seed(0)
DEBUG = False


def batchify(fn, chunk):
    """
    Constructs a version of 'fn' that applies to smaller batches.
    """
    if chunk is None:
        return fn
    def ret(inputs):
        return torch.cat([fn(inputs[i:i+chunk]) for i in range(0, inputs.shape[0], chunk)], 0)
    return ret


def run_network(inputs, viewdirs, fn, embed_fn, embeddirs_fn, netchunk=1024*64):
    """
    Prepares inputs and applies network 'fn'.
    """
    inputs_flat = torch.reshape(inputs, [-1, inputs.shape[-1]])
    embedded = embed_fn(inputs_flat)

    if viewdirs is not None:
        input_dirs = viewdirs[:,None].expand(inputs.shape)
        input_dirs_flat = torch.reshape(input_dirs, [-1, input_dirs.shape[-1]])
        embedded_dirs = embeddirs_fn(input_dirs_flat)
        embedded = torch.cat([embedded, embedded_dirs], -1)

    outputs_flat = batchify(fn, netchunk)(embedded)
    outputs = torch.reshape(outputs_flat, list(inputs.shape[:-1]) + [outputs_flat.shape[-1]])
    return outputs


def batchify_rays(rays_flat, chunk=1024*32, **kwargs):
    """
    Render rays in smaller minibatches to avoid OOM.
    """
    all_ret = {}
    for i in range(0, rays_flat.shape[0], chunk):
        ret = render_rays(rays_flat[i:i+chunk], **kwargs)
        for k in ret:
            if k not in all_ret:
                all_ret[k] = []
            all_ret[k].append(ret[k])

    all_ret = {k : torch.cat(all_ret[k], 0) for k in all_ret}
    return all_ret


def render(H, W, K, chunk=1024*32, rays=None, c2w=None, ndc=True,
                near=0., far=1.,
                use_viewdirs=False, c2w_staticcam=None,
                  **kwargs):
    """
    Render rays
    Args:
        H: int. Height of image in pixels.
        W: int. Width of image in pixels.
            focal: float. Focal length of pinhole camera.
            chunk: int. Maximum number of rays to process simultaneously. Used to
            control maximum memory usage. Does not affect final results.
        rays: array of shape [2, batch_size, 3]. Ray origin and direction for
            each example in batch.
        c2w: array of shape [3, 4]. Camera-to-world transformation matrix.
        ndc: bool. If True, represent ray origin, direction in NDC coordinates.
        near: float or array of shape [batch_size]. Nearest distance for a ray.
        far: float or array of shape [batch_size]. Farthest distance for a ray.
        use_viewdirs: bool. If True, use viewing direction of a point in space in model.
        c2w_staticcam: array of shape [3, 4]. If not None, use this transformation matrix for 
        camera while using other c2w argument for viewing directions.
    Returns:
        rgb_map: [batch_size, 3]. Predicted RGB values for rays.
        disp_map: [batch_size]. Disparity map. Inverse of depth.
        acc_map: [batch_size]. Accumulated opacity (alpha) along a ray.
        extras: dict with everything returned by render_rays().
    """
    if c2w is not None:
        # special case to render full image
        rays_o, rays_d = get_rays(H, W, K, c2w)
    else:
        # use provided ray batch
        rays_o, rays_d = rays

    if use_viewdirs:
        # provide ray directions as input
        viewdirs = rays_d
        if c2w_staticcam is not None:
            # special case to visualize effect of viewdirs
            rays_o, rays_d = get_rays(H, W, K, c2w_staticcam)
        viewdirs = viewdirs / torch.norm(viewdirs, dim=-1, keepdim=True)
        viewdirs = torch.reshape(viewdirs, [-1,3]).float()

    sh = rays_d.shape # [..., 3]
    if ndc:
        # for forward facing scenes
        rays_o, rays_d = ndc_rays(H, W, K[0][0], 1., rays_o, rays_d)

    # Create ray batch
    rays_o = torch.reshape(rays_o, [-1,3]).float()
    rays_d = torch.reshape(rays_d, [-1,3]).float()

    near, far = near * torch.ones_like(rays_d[...,:1]), far * torch.ones_like(rays_d[...,:1])
    rays = torch.cat([rays_o, rays_d, near, far], -1)
    if use_viewdirs:
        rays = torch.cat([rays, viewdirs], -1)

    # Render and reshape
    all_ret = batchify_rays(rays, chunk, **kwargs)
    for k in all_ret:
        k_sh = list(sh[:-1]) + list(all_ret[k].shape[1:])
        all_ret[k] = torch.reshape(all_ret[k], k_sh)

    k_extract = ['rgb_map', 'disp_map', 'acc_map']
    ret_list = [all_ret[k] for k in k_extract]
    ret_dict = {k : all_ret[k] for k in all_ret if k not in k_extract}
    return ret_list + [ret_dict]


def render_path(render_poses, hwf, K, chunk, render_kwargs,
                gt_imgs=None, 
                savedir=None, 
                render_factor=0, 
                img_prefix='',
                img_suffix='',
                save_depths=False
                ):

    H, W, focal = hwf

    if render_factor!=0:
        # Render downsampled for speed
        H = H//render_factor
        W = W//render_factor
        focal = focal/render_factor

    rgbs = []
    disps = []
    depths = []

    t = time.time()
    for i, c2w in enumerate(tqdm(render_poses,desc='Rendering poses: ')):
        if DEBUG:
            print(i, time.time() - t)
        t = time.time()
        rgb, disp, acc, ret = render(H, W, K, chunk=chunk, c2w=c2w[:3,:4], **render_kwargs)
        rgbs.append(rgb.cpu().numpy())
        disps.append(disp.cpu().numpy())
        depths.append(ret['depth_map'].cpu().numpy())
        # print(torch.max(rgb), type(rgb))
        # print(torch.max(disp), type(disp))
        # print(ret['depth_map'].shape, type(ret['depth_map']))
        # print(torch.max(ret['depth_map']))
        
        # assert False, "BREAK"
        if DEBUG and i==0:
            print(rgb.shape, disp.shape)

        if savedir is not None:
            rgb8 = to8b(rgbs[-1])
            filename = path_join(savedir, img_prefix+'{:03d}.png'.format(i))
            imageio.imwrite(filename, rgb8)
            wandb.log({img_prefix+'{:03d}.png'.format(i): wandb.Image(filename)})
            if save_depths:
                filename = path_join(savedir, img_prefix+'{:03d}_depth.png'.format(i))
                imageio.imwrite(filename, to8b(depths[-1]))
                wandb.log({
                    img_prefix+'{:03d}_depth.png'.format(i): wandb.Image(filename)
                    })
    
    rgbs = np.stack(rgbs, 0)
    disps = np.stack(disps, 0)
    depths = np.stack(depths, 0)

    if gt_imgs is not None and render_factor==0:
        with torch.no_grad():
            if isinstance(gt_imgs,torch.Tensor):
                gt_imgs = gt_imgs.cpu()
            gts = np.stack(gt_imgs,0)
            val_loss = np.mean((rgbs-gts)**2)
            val_psnr = -10. * np.log10(val_loss)
            output = f'[{img_prefix}] Iter: {img_suffix} Loss: {val_loss:.3f} {img_prefix} PSNR: {val_psnr:.3f}'

            print(output)
            wandb.log({
                f'{img_prefix}/Iter': img_suffix,
                f'{img_prefix}/Loss': val_loss,
                f'{img_prefix}/PSNR': val_psnr
            })

    return rgbs, disps, depths


def create_nerf(args):
    """
    Instantiate NeRF's MLP model.
    """
    embed_fn, input_ch = get_embedder(args.multires, args.i_embed)

    input_ch_views = 0
    embeddirs_fn = None
    if args.use_viewdirs:
        embeddirs_fn, input_ch_views = get_embedder(args.multires_views, args.i_embed)
    output_ch = 5 if args.N_importance > 0 else 4
    skips = [4]
    model = NeRF(D=args.netdepth, W=args.netwidth,
                    input_ch=input_ch, output_ch=output_ch, skips=skips,
                    input_ch_views=input_ch_views, use_viewdirs=args.use_viewdirs).to(device)
    grad_vars = list(model.parameters())

    model_fine = None
    if args.N_importance > 0:
        model_fine = NeRF(D=args.netdepth_fine, W=args.netwidth_fine,
                            input_ch=input_ch, output_ch=output_ch, skips=skips,
                            input_ch_views=input_ch_views, use_viewdirs=args.use_viewdirs).to(device)
        grad_vars += list(model_fine.parameters())

    network_query_fn = lambda inputs, viewdirs, network_fn : run_network(inputs, viewdirs, network_fn,
                                                                embed_fn=embed_fn,
                                                                embeddirs_fn=embeddirs_fn,
                                                                netchunk=args.netchunk)

    # Create optimizer
    optimizer = torch.optim.Adam(params=grad_vars, lr=args.lrate, betas=(0.9, 0.999))

    start = 0
    basedir = args.basedir
    expname = args.expname

    ##########################

    # Load checkpoints
    if args.ft_path is not None and args.ft_path!='None':
        ckpts = [args.ft_path]
    else:
        ckpts = [path_join(basedir, expname, f) for f in sorted(listdir(path_join(basedir, expname))) if 'tar' in f]
    
    if len(ckpts) > 0 and not args.no_reload:
        print('Found ckpts')
        ckpt_path = ckpts[-1]
        print('Reloading from', ckpt_path)
        wandb.log({'Reloading from': ckpt_path})
        ckpt = torch.load(ckpt_path)

        start = ckpt['global_step']
        optimizer.load_state_dict(ckpt['optimizer_state_dict'])

        # Load model
        model.load_state_dict(ckpt['network_fn_state_dict'])
        if model_fine is not None:
            model_fine.load_state_dict(ckpt['network_fine_state_dict'])

    ##########################

    render_kwargs_train = {
        'network_query_fn' : network_query_fn,
        'perturb' : args.perturb,
        'N_importance' : args.N_importance,
        'network_fine' : model_fine,
        'N_samples' : args.N_samples,
        'network_fn' : model,
        'use_viewdirs' : args.use_viewdirs,
        'white_bkgd' : args.white_bkgd,
        'raw_noise_std' : args.raw_noise_std,
    }

    # NDC only good for LLFF-style forward facing data
    if args.dataset_type != 'llff' or args.no_ndc:
        print('Not ndc!')
        render_kwargs_train['ndc'] = False
        render_kwargs_train['lindisp'] = args.lindisp

    render_kwargs_test = {k : render_kwargs_train[k] for k in render_kwargs_train}
    render_kwargs_test['perturb'] = False
    render_kwargs_test['raw_noise_std'] = 0.

    wandb.watch(model,log='all')
    # change render_kwargs_train
    return render_kwargs_train, render_kwargs_test, start, grad_vars, optimizer


def raw2outputs(raw, z_vals, rays_d, raw_noise_std=0, white_bkgd=False, pytest=False):
    """
    Transforms model's predictions to semantically meaningful values.
    Args:
        raw: [num_rays, num_samples along ray, 4]. Prediction from model.
        z_vals: [num_rays, num_samples along ray]. Integration time.
        rays_d: [num_rays, 3]. Direction of each ray.
    Returns:
        rgb_map: [num_rays, 3]. Estimated RGB color of a ray.
        disp_map: [num_rays]. Disparity map. Inverse of depth map.
        acc_map: [num_rays]. Sum of weights along each ray.
        weights: [num_rays, num_samples]. Weights assigned to each sampled color.
        depth_map: [num_rays]. Estimated distance to object.
    """
    raw2alpha = lambda raw, dists, act_fn=relu_func: 1.-torch.exp(-act_fn(raw)*dists)

    dists = z_vals[...,1:] - z_vals[...,:-1]
    dists = torch.cat([dists, torch.Tensor([1e10]).expand(dists[...,:1].shape)], -1)  # [N_rays, N_samples]

    dists = dists * torch.norm(rays_d[...,None,:], dim=-1)

    rgb = torch.sigmoid(raw[...,:3])  # [N_rays, N_samples, 3]
    noise = 0.
    if raw_noise_std > 0.:
        noise = torch.randn(raw[...,3].shape) * raw_noise_std

        # Overwrite randomly sampled data if pytest
        if pytest:
            np.random.seed(0)
            noise = np.random.rand(*list(raw[...,3].shape)) * raw_noise_std
            noise = torch.Tensor(noise)

    alpha = raw2alpha(raw[...,3] + noise, dists)  # [N_rays, N_samples]
    # weights = alpha * tf.math.cumprod(1.-alpha + 1e-10, -1, exclusive=True)
    weights = alpha * torch.cumprod(torch.cat([torch.ones((alpha.shape[0], 1)), 1.-alpha + 1e-10], -1), -1)[:, :-1]
    rgb_map = torch.sum(weights[...,None] * rgb, -2)  # [N_rays, 3]

    depth_map = torch.sum(weights * z_vals, -1)
    # disp_map = 1./torch.max(1e-10 * torch.ones_like(depth_map), depth_map / torch.sum(weights, -1))
    disp_map = depth2dist(depth_map,weights)
    acc_map = torch.sum(weights, -1)

    if white_bkgd:
        rgb_map = rgb_map + (1.-acc_map[...,None])

    return rgb_map, disp_map, acc_map, weights, depth_map


def render_rays(ray_batch,
                network_fn,
                network_query_fn,
                N_samples,
                ret_raw=False,
                lindisp=False,
                perturb=0.,
                N_importance=0,
                network_fine=None,
                white_bkgd=False,
                raw_noise_std=0.,
                verbose=False,
                pytest=False):
    """Volumetric rendering.
    Args:
        ray_batch: array of shape [batch_size, ...]. All information necessary
            for sampling along a ray, including: ray origin, ray direction, min
            dist, max dist, and unit-magnitude viewing direction.
        network_fn: function. Model for predicting RGB and density at each point
            in space.
        network_query_fn: function used for passing queries to network_fn.
        N_samples: int. Number of different times to sample along each ray.
        ret_raw: bool. If True, include model's raw, unprocessed predictions.
        lindisp: bool. If True, sample linearly in inverse depth rather than in depth.
        perturb: float, 0 or 1. If non-zero, each ray is sampled at stratified
            random points in time.
        N_importance: int. Number of additional times to sample along each ray.
            These samples are only passed to network_fine.
        network_fine: "fine" network with same spec as network_fn.
        white_bkgd: bool. If True, assume a white background.
        raw_noise_std: ...
        verbose: bool. If True, print more debugging info.
    Returns:
        rgb_map: [num_rays, 3]. Estimated RGB color of a ray. Comes from fine model.
        disp_map: [num_rays]. Disparity map. 1 / depth.
        acc_map: [num_rays]. Accumulated opacity along each ray. Comes from fine model.
        raw: [num_rays, num_samples, 4]. Raw predictions from model.
        rgb0: See rgb_map. Output for coarse model.
        disp0: See disp_map. Output for coarse model.
        acc0: See acc_map. Output for coarse model.
        z_std: [num_rays]. Standard deviation of distances along ray for each
            sample.
    """
    N_rays = ray_batch.shape[0]
    rays_o, rays_d = ray_batch[:,0:3], ray_batch[:,3:6] # [N_rays, 3] each
    viewdirs = ray_batch[:,-3:] if ray_batch.shape[-1] > 8 else None
    bounds = torch.reshape(ray_batch[...,6:8], [-1,1,2])
    near, far = bounds[...,0], bounds[...,1] # [-1,1]

    t_vals = torch.linspace(0., 1., steps=N_samples)
    if not lindisp:
        z_vals = near * (1.-t_vals) + far * (t_vals)
    else:
        z_vals = 1./(1./near * (1.-t_vals) + 1./far * (t_vals))

    z_vals = z_vals.expand([N_rays, N_samples])

    if perturb > 0.:
        # get intervals between samples
        mids = .5 * (z_vals[...,1:] + z_vals[...,:-1])
        upper = torch.cat([mids, z_vals[...,-1:]], -1)
        lower = torch.cat([z_vals[...,:1], mids], -1)
        # stratified samples in those intervals
        t_rand = torch.rand(z_vals.shape)

        # Pytest, overwrite u with numpy's fixed random numbers
        if pytest:
            np.random.seed(0)
            t_rand = np.random.rand(*list(z_vals.shape))
            t_rand = torch.Tensor(t_rand)

        z_vals = lower + (upper - lower) * t_rand

    pts = rays_o[...,None,:] + rays_d[...,None,:] * z_vals[...,:,None] # [N_rays, N_samples, 3]


#     raw = run_network(pts)
    raw = network_query_fn(pts, viewdirs, network_fn)
    rgb_map, disp_map, acc_map, weights, depth_map = raw2outputs(raw, z_vals, rays_d, raw_noise_std, white_bkgd, pytest=pytest)

    if N_importance > 0:

        rgb_map_0, disp_map_0, acc_map_0 = rgb_map, disp_map, acc_map

        z_vals_mid = .5 * (z_vals[...,1:] + z_vals[...,:-1])
        z_samples = sample_pdf(z_vals_mid, weights[...,1:-1], N_importance, det=(perturb==0.), pytest=pytest)
        z_samples = z_samples.detach()

        z_vals, _ = torch.sort(torch.cat([z_vals, z_samples], -1), -1)
        pts = rays_o[...,None,:] + rays_d[...,None,:] * z_vals[...,:,None] # [N_rays, N_samples + N_importance, 3]

        run_fn = network_fn if network_fine is None else network_fine
#         raw = run_network(pts, fn=run_fn)
        raw = network_query_fn(pts, viewdirs, run_fn)

        rgb_map, disp_map, acc_map, weights, depth_map = raw2outputs(raw, z_vals, rays_d, raw_noise_std, white_bkgd, pytest=pytest)

    ret = {'rgb_map' : rgb_map, 'disp_map' : disp_map, 'acc_map' : acc_map, 'depth_map' : depth_map}
    if ret_raw:
        ret['raw'] = raw
    if N_importance > 0:
        ret['rgb0'] = rgb_map_0
        ret['disp0'] = disp_map_0
        ret['acc0'] = acc_map_0
        ret['z_std'] = torch.std(z_samples, dim=-1, unbiased=False)  # [N_rays]

    for k in ret:
        if (torch.isnan(ret[k]).any() or torch.isinf(ret[k]).any()) and DEBUG:
            print(f"! [Numerical Error] {k} contains nan or inf.")

    return ret


def train(args):
    # TODO: add depthmapping
    # https://keras.io/examples/vision/nerf/

    images, poses, render_poses, hwf, K, i_split, near, far = load_data_from_args(args)
    i_train, i_val, i_test = i_split
    H, W, _ = hwf 
    if args.render_poses_filter and np.max(args.render_poses_filter) > len(i_test):
        raise ValueError(f"args.render_poses_filter must be <= len(i_test)")
        
    # Create log dir and copy the config file
    basedir = args.basedir
    expname = args.expname
    makedirs(path_join(basedir, expname), exist_ok=True)
    
    file_path = path_join(basedir, expname, 'args.txt')
    with open(file_path, 'w') as file:
        for arg in sorted(vars(args)):
            attr = getattr(args, arg)
            file.write('{} = {}\n'.format(arg, attr))
    if args.config is not None:
        file_path = path_join(basedir, expname, 'config.txt')
        with open(file_path, 'w') as file:
            file.write(open(args.config, 'r').read())
    wandb.init(
        project='C291 NeRF', 
        name=expname, 
        dir=path_join(basedir, expname), 
        config=vars(args)
    )
    # Create nerf model
    # grad_vars unused
    render_kwargs_train, render_kwargs_test, start, _, nerf_optimizer = create_nerf(args)
    global_step = start

    bds_dict = {
        'near' : near,
        'far' : far,
    }
    render_kwargs_train.update(bds_dict)
    render_kwargs_test.update(bds_dict)

    # Move testing data to GPU
    render_poses = torch.Tensor(render_poses).to(device)

    # Short circuit if only rendering out from trained model
    if args.render_only:
        print('RENDER ONLY')
        with torch.no_grad():
            if args.render_test:
                # render_test switches to test poses
                images = images[i_test]
            else:
                # Default is smoother render_poses path
                images = None

            testsavedir = path_join(basedir, expname, 'renderonly_{}_{:06d}'.format('test' if args.render_test else 'path', start))
            makedirs(testsavedir, exist_ok=True)
            print('test poses shape', render_poses[args.render_poses_filter].shape)

            rgbs, _, depths = render_path(render_poses[args.render_poses_filter], hwf, K, args.chunk, render_kwargs_test, gt_imgs=images, savedir=testsavedir, render_factor=args.render_factor)

            depths = np.repeat(np.expand_dims(depths,axis=3),3,axis=3)
            # because rgbs may be slightly over 1
            imageio.mimwrite(path_join(testsavedir, 'rbgs_video.mp4'), to8b(rgbs/np.max(rgbs)), fps=30, quality=8)
            imageio.mimwrite(path_join(testsavedir, 'depths_video.mp4'), to8b(depths/np.max(depths)), fps=30, quality=8)
            # logs
            wandb.log(
                {
                    "render_only_rbgs_gif": wandb.Video(rgbs, fps=30, format='gif'),
                    "render_only_depths_gif": wandb.Video(depths, fps=30, format='gif'),
                    "render_only_rbgs_mp4": wandb.Video(path_join(testsavedir, 'rbgs_video.mp4'), fps=10, format='mp4'),
                    "render_only_depths_mp4": wandb.Video(path_join(testsavedir, 'depths_video.mp4'), fps=10, format='mp4'),
                }
            )
            # early break
            return

    # Prepare raybatch tensor if batching random rays
    N_rand = args.N_rand
    use_batching = not args.no_batching
    if use_batching:
        # For random ray batching
        print('get rays')
        rays = np.stack([get_rays_np(H, W, K, p) for p in poses[:,:3,:4]], 0) # [N, ro+rd, H, W, 3]
        print('done, concats')
        # added for bottles dataset
        if rays.shape[0] > images[:,None].shape[0]:
            rays = rays[:images[:,None].shape[0]]
        # print(rays.shape, images[:,None].shape)
        rays_rgb = np.concatenate([rays, images[:,None]], 1) # [N, ro+rd+rgb, H, W, 3]
        rays_rgb = np.transpose(rays_rgb, [0,2,3,1,4]) # [N, H, W, ro+rd+rgb, 3]
        rays_rgb = np.stack([rays_rgb[i] for i in i_train], 0) # train images only
        rays_rgb = np.reshape(rays_rgb, [-1,3,3]) # [(N-1)*H*W, ro+rd+rgb, 3]
        rays_rgb = rays_rgb.astype(np.float32)
        print('shuffle rays')
        np.random.shuffle(rays_rgb)

        print('done')
        i_batch = 0

        # Move training data to GPU
        images = torch.Tensor(images).to(device)
        rays_rgb = torch.Tensor(rays_rgb).to(device)


    poses = torch.Tensor(poses).to(device)

    if args.i_val_eval > 0:
        val_imgs = images[i_val[:args.i_val_set]]
        val_poses = poses[i_val[:args.i_val_set]]

    N_iters = args.n_iters + 1
    print('Begin')
    print('TRAIN views are', i_train)
    print('TEST views are', i_test)
    print('VAL views are', i_val)

    # Summary writers
    # writer = SummaryWriter(path_join(basedir, 'summaries', expname))
    
    start = start + 1
    for i in range(start, N_iters):
        time0 = time.time()

        # Sample random ray batch
        if use_batching:
            # Random over all images
            batch = rays_rgb[i_batch:i_batch+N_rand] # [B, 2+1, 3*?]
            batch = torch.transpose(batch, 0, 1)
            batch_rays, target_s = batch[:2], batch[2]

            i_batch += N_rand
            if i_batch >= rays_rgb.shape[0]:
                print("Shuffle data after an epoch!")
                rand_idx = torch.randperm(rays_rgb.shape[0])
                rays_rgb = rays_rgb[rand_idx]
                i_batch = 0

        else:
            # Random from one image
            img_i = np.random.choice(i_train)
            target = images[img_i]
            target = torch.Tensor(target).to(device)
            pose = poses[img_i, :3,:4]

            if N_rand is not None:
                rays_o, rays_d = get_rays(H, W, K, torch.Tensor(pose))  # (H, W, 3), (H, W, 3)

                if i < args.precrop_iters:
                    dH = int(H//2 * args.precrop_frac)
                    dW = int(W//2 * args.precrop_frac)
                    coords = torch.stack(
                        torch.meshgrid(
                            torch.linspace(H//2 - dH, H//2 + dH - 1, 2*dH), 
                            torch.linspace(W//2 - dW, W//2 + dW - 1, 2*dW),
                            indexing = 'ij'
                        ), -1)
                    if i == start:
                        print(f"[Config] Center cropping of size {2*dH} x {2*dW} is enabled until iter {args.precrop_iters}")                
                else:
                    coords = torch.stack(torch.meshgrid(
                                            torch.linspace(0, H-1, H), 
                                            torch.linspace(0, W-1, W),
                                            indexing='ij')
                                        , -1)  # (H, W, 2)

                coords = torch.reshape(coords, [-1,2])  # (H * W, 2)
                select_inds = np.random.choice(coords.shape[0], size=[N_rand], replace=False)  # (N_rand,)
                select_coords = coords[select_inds].long()  # (N_rand, 2)
                rays_o = rays_o[select_coords[:, 0], select_coords[:, 1]]  # (N_rand, 3)
                rays_d = rays_d[select_coords[:, 0], select_coords[:, 1]]  # (N_rand, 3)
                batch_rays = torch.stack([rays_o, rays_d], 0)
                target_s = target[select_coords[:, 0], select_coords[:, 1]]  # (N_rand, 3)

        #####  Core optimization loop  #####
        rgb, disp, acc_map, extras = render(H, W, K, chunk=args.chunk, rays=batch_rays,
                                                verbose=i < 10, ret_raw=True,
                                                **render_kwargs_train)

        nerf_optimizer.zero_grad()
        img_loss = img2mse(rgb, target_s)
        trans = extras['raw'][...,-1]
        train_loss = img_loss
        train_psnr = mse2psnr(img_loss)
        
        if 'rgb0' in extras:
            img_loss0 = img2mse(extras['rgb0'], target_s)
            train_loss = train_loss + img_loss0
            psnr0 = mse2psnr(img_loss0)

        train_loss.backward()
        nerf_optimizer.step()

        # NOTE: IMPORTANT!
        ###   update learning rate   ###
        decay_rate = 0.1
        decay_steps = args.lrate_decay * 1000
        new_lrate = args.lrate * (decay_rate ** (global_step / decay_steps))
        for param_group in nerf_optimizer.param_groups:
            param_group['lr'] = new_lrate
        ################################

        dt = time.time()-time0
        # print(f"Step: {global_step}, Loss: {loss}, Time: {dt}")
        #####           end            #####

        ##### Rest is logging

        if i%args.i_print==0:
            outstring =f"[TRAIN] Iter: {i} Loss: {train_loss.item()} PSNR: {train_psnr.item()} Iter time: {dt:.05f}" 
            tqdm.write(outstring)
            wandb.log({
                "TRAIN/Iter": i,
                "TRAIN/Loss": train_loss.item(),
                "TRAIN/PSNR": train_psnr.item(),
                "TRAIN/Iter time": dt
            })

        # logging weights
        if i%args.i_weights==0:
            path = path_join(basedir, expname, '{:06d}.tar'.format(i))
            torch.save({
                'global_step': global_step,
                'network_fn_state_dict': render_kwargs_train['network_fn'].state_dict(),
                'network_fine_state_dict': render_kwargs_train['network_fine'].state_dict(),
                'optimizer_state_dict': nerf_optimizer.state_dict(),
            }, path)
            wandb.save("model_iter_{:06d}.tar".format(i))
            print('Saved checkpoints at', path)

        # TODO: Consolidate code
        if i%args.i_video==0 and i > 0:
            # Turn on testing mode
            print('video')
            with torch.no_grad():
                rgbs, _, depths = render_path(render_poses, hwf, K, args.chunk, render_kwargs_test)

            print('Done, saving', rgbs.shape, depths.shape)
            moviebase = path_join(basedir, expname, '{}_spiral_{:06d}_'.format(expname, i))
            imageio.mimwrite(moviebase + 'rgb.mp4', to8b(rgbs), fps=30, quality=8)
            imageio.mimwrite(moviebase + 'depth.mp4', to8b(depths / np.max(depths)), fps=30, quality=8)
            wandb.log({
                '{}_spiral_{:06d}_'.format(expname, i)+'rgb.gif': wandb.Video(moviebase + 'rgb.mp4', format='gif'),
                '{}_spiral_{:06d}_'.format(expname, i)+'disp.gif': wandb.Video(moviebase + 'depth.mp4', format='gif'),
                '{}_spiral_{:06d}_'.format(expname, i)+'rgb.mp4': wandb.Video(moviebase + 'rgb.mp4'),
                '{}_spiral_{:06d}_'.format(expname, i)+'depth.mp4': wandb.Video(moviebase + 'depth.mp4'),
            })
            if args.use_viewdirs:
                print('static video')
                render_kwargs_test['c2w_staticcam'] = render_poses[30][:3,:4]
                with torch.no_grad():
                    rgbs_still, *_ = render_path(render_poses, hwf, K ,args.chunk, render_kwargs_test)

                render_kwargs_test['c2w_staticcam'] = None
                imageio.mimwrite(moviebase + 'rgb_still.mp4', to8b(rgbs_still), fps=30, quality=8)
                wandb.log({
                    '{}_spiral_{:06d}_'.format(expname, i)+'rgb_still.gif': wandb.Video(moviebase + 'rgb_still.mp4', format='gif'),
                    '{}_spiral_{:06d}_'.format(expname, i)+'rgb_still.mp4': wandb.Video(moviebase + 'rgb_still.mp4'),
                })

        if i%args.i_testset==0 and i > 0:
            testsavedir = path_join(basedir, expname, 'testset_{:06d}'.format(i))
            makedirs(testsavedir, exist_ok=True)
            inds = i_test
            if args.render_poses_filter:
                inds = i_test[args.render_poses_filter]
            with torch.no_grad():
                pose_filter = torch.Tensor(poses[inds]).to(device)
                render_path(pose_filter, hwf, K, args.chunk, render_kwargs_test,
                                # gt_imgs=images[i_test], 
                                savedir=testsavedir)
                pose_filter = pose_filter.cpu()
                del pose_filter
            print('Saved test set')
    
        if args.i_val_eval and i%args.i_val_eval==0 and i > 0:
            print("Evaluating on validation set")
            filename = path_join(basedir, expname, 'val_eval_{:06d}'.format(i))
            mkdir(filename)
            with torch.no_grad():
                render_path(val_poses, hwf, K, args.chunk, render_kwargs_train,
                                            gt_imgs=val_imgs,
                                            img_prefix=f'VAL',
                                            img_suffix=i,
                                            savedir=filename
                                            )

    
            
        """
            with tf.contrib.summary.record_summaries_every_n_global_steps(args.i_print):
                tf.contrib.summary.scalar('loss', loss)
                tf.contrib.summary.scalar('psnr', psnr)
                tf.contrib.summary.histogram('tran', trans)
                if args.N_importance > 0:
                    tf.contrib.summary.scalar('psnr0', psnr0)


            if i%args.i_img==0:

                # Log a rendered validation view to Tensorboard
                img_i=np.random.choice(i_val)
                target = images[img_i]
                pose = poses[img_i, :3,:4]
                with torch.no_grad():
                    rgb, disp, acc, extras = render(H, W, focal, chunk=args.chunk, c2w=pose,
                                                        **render_kwargs_test)

                psnr = mse2psnr(img2mse(rgb, target))

                with tf.contrib.summary.record_summaries_every_n_global_steps(args.i_img):

                    tf.contrib.summary.image('rgb', to8b(rgb)[tf.newaxis])
                    tf.contrib.summary.image('disp', disp[tf.newaxis,...,tf.newaxis])
                    tf.contrib.summary.image('acc', acc[tf.newaxis,...,tf.newaxis])

                    tf.contrib.summary.scalar('psnr_holdout', psnr)
                    tf.contrib.summary.image('rgb_holdout', target[tf.newaxis])


                if args.N_importance > 0:

                    with tf.contrib.summary.record_summaries_every_n_global_steps(args.i_img):
                        tf.contrib.summary.image('rgb0', to8b(extras['rgb0'])[tf.newaxis])
                        tf.contrib.summary.image('disp0', extras['disp0'][tf.newaxis,...,tf.newaxis])
                        tf.contrib.summary.image('z_std', extras['z_std'][tf.newaxis,...,tf.newaxis])
        """

        global_step += 1


if __name__=='__main__':
    parser = config_parser()
    args = parser.parse_args()

    device = torch.device((f'cuda:{args.gpu}' if torch.cuda.is_available() else 'cpu'))
    print(f'using device {device}')
    with torch.cuda.device(args.gpu):
        torch.set_default_tensor_type('torch.cuda.FloatTensor')
        train(args)
    