# -*- coding: utf8 -*-
# author: ronniecao
from __future__ import print_function
import sys
import os
import time
import pickle
import math
import numpy
import random
import matplotlib.pyplot as plt
import platform
import cv2
from threading import Thread

if 'Windows' in platform.platform():
    from queue import Queue
elif 'Linux' in platform.platform():
    from Queue import Queue


class ImageProcessor:
    
    def __init__(self, directory, image_size=288, max_objects_per_image=20, cell_size=7,
                 n_classes=1):
        # 参数赋值
        self.image_size = image_size
        self.max_objects = max_objects_per_image
        self.cell_size = cell_size
        self.n_classes = n_classes
        
        self.load_images_labels(directory)
    
    def load_images_labels(self, directory):
        if os.path.exists(directory):
            # 读取训练集
            train_file = os.path.join(directory, 'train.txt')
            self.load_dataset_loop(train_file, n_thread=5)
            
            # 读取验证集
            valid_file = os.path.join(directory, 'valid.txt')
            self.valid_images, self.valid_class_labels, self.valid_class_masks, \
                self.valid_box_labels, self.valid_object_masks, \
                self.valid_nobject_masks, self.valid_object_nums = \
                    self.load_dataset_whole(valid_file, n_thread=5)
            self.n_valid = self.valid_images.shape[0]
            
            # 读取测试集
            test_file = os.path.join(directory, 'test.txt')
            self.test_images, self.test_class_labels, self.test_class_masks, \
                self.test_box_labels, self.test_object_masks, \
                self.test_nobject_masks, self.test_object_nums = \
                    self.load_dataset_whole(test_file, n_thread=5)
            self.n_test = self.test_images.shape[0]
            
            print('valid images: ', self.valid_images.shape, 
                  ', valid class labels: ', self.valid_class_labels.shape, 
                  ', valid class masks: ', self.valid_class_masks.shape,
                  ', valid box labels: ', self.valid_box_labels.shape,
                  ', valid object masks: ', self.valid_object_masks.shape,
                  ', valid nobject masks: ', self.valid_nobject_masks.shape,
                  ', valid object num: ', self.valid_object_nums.shape)
            print('test images: ', self.test_images.shape, 
                  ', test class labels: ', self.test_class_labels.shape, 
                  ', test class masks: ', self.test_class_masks.shape,
                  ', test box labels: ', self.test_box_labels.shape,
                  ', test object masks: ', self.test_object_masks.shape,
                  ', test nobject masks: ', self.test_nobject_masks.shape,
                  ', test object nums: ', self.test_object_nums.shape)
            print()
            sys.stdout.flush()
        
    def load_dataset_whole(self, filename, n_thread=10):
        # 读取训练集/验证集/测试集
        # 该函数使用多线程，将所有数据全部载入内存，不使用缓冲区
        
        info_list = Queue(maxsize=20000)
        dataset = Queue(maxsize=20000)
        
        # 读取info_list
        with open(filename, 'r') as fo:
            for line in fo:
                infos = line.strip().split(' ')
                info_list.put(infos)
        
        def _process(name):
            
            while not info_list.empty():
                
                infos = info_list.get()
                image_path = infos[0]
                label_infos = infos[1:]
                
                # 读取图像
                image = cv2.imread(image_path)
                [image_h, image_w, _] = image.shape
                image = cv2.resize(image, (self.image_size, self.image_size))
                
                # 处理 label
                i, n_objects = 0, 0
                label = [[0, 0, 0, 0, 0]] * self.max_objects
                while i < len(label_infos) and n_objects < self.max_objects:
                    xmin = int(label_infos[i])
                    ymin = int(label_infos[i+1])
                    xmax = int(label_infos[i+2])
                    ymax = int(label_infos[i+3])
                    class_index = int(label_infos[i+4])
                    
                    # 转化成 center_x, center_y, w, h
                    center_x = (1.0 * (xmin + xmax) / 2.0) / image_w
                    center_y = (1.0 * (ymin + ymax) / 2.0) / image_h
                    w = (1.0 * (xmax - xmin)) / image_w
                    h = (1.0 * (ymax - ymin)) / image_h
                    
                    label[n_objects] = [center_x, center_y, w, h, class_index]
                    i += 5
                    n_objects += 1
                
                class_label, class_mask, box_label, object_mask, nobject_mask, object_num = \
                    self.process_label(label)
                    
                dataset.put([image, class_label, class_mask, box_label, 
                             object_mask, nobject_mask, object_num])
                
        # 以多线程的方式进行数据预处理
        thread_list = []
        for i in range(n_thread):
            thread = Thread(target=_process, args=(i,))
            thread_list.append(thread)
        for thread in thread_list:
            thread.start()
        for thread in thread_list:
            thread.join()
        
        # 处理dataset，将其分解成images和labels
        images, class_labels, class_masks, box_labels, \
            object_masks, nobject_masks, object_nums = [], [], [], [], [], [], []
        while not dataset.empty():
            image, class_label, class_mask, box_label, \
                object_mask, nobject_mask, object_num = dataset.get()
            images.append(image)
            class_labels.append(class_label)
            class_masks.append(class_mask)
            box_labels.append(box_label)
            object_masks.append(object_mask)
            nobject_masks.append(nobject_mask)
            object_nums.append(object_num)
        
        images = numpy.array(images, dtype='uint8')
        class_labels = numpy.array(class_labels, dtype='int32')
        class_masks = numpy.array(class_masks, dtype='float32')
        box_labels = numpy.array(box_labels, dtype='float32')
        object_masks = numpy.array(object_masks, dtype='float32')
        nobject_masks = numpy.array(nobject_masks, dtype='float32')
        object_nums = numpy.array(object_nums, dtype='int32')
        
        return images, class_labels, class_masks, box_labels, \
            object_masks, nobject_masks, object_nums
        
    def load_dataset_loop(self, filename, n_thread=10):
        # 读取训练集/验证集/测试集
        # 该函数使用多线程，基于生产者消费者模型
        # 生产者不停地读取原始数据，并且处理数据，并且存入循环队列中
        # 消费者从循环队列中读取batch后，直接传入模型进行训练
        
        info_list = []
        self.train_dataset = Queue(maxsize=10000)
        
        # 读取info_list
        with open(filename, 'r') as fo:
            for line in fo:
                infos = line.strip().split(' ')
                info_list.append(infos)
        
        def _produce(name):
            while True:
                random.shuffle(info_list)
                
                for infos in info_list:
                    image_path = infos[0]
                    label_infos = infos[1:]
                    
                    # 读取图像
                    image = cv2.imread(image_path)
                    [image_h, image_w, _] = image.shape
                    image = cv2.resize(image, (self.image_size, self.image_size))
                    
                    # 处理 label
                    i, n_objects = 0, 0
                    label = [[0, 0, 0, 0, 0]] * self.max_objects
                    while i < len(label_infos) and n_objects < self.max_objects:
                        xmin = int(label_infos[i])
                        ymin = int(label_infos[i+1])
                        xmax = int(label_infos[i+2])
                        ymax = int(label_infos[i+3])
                        class_index = int(label_infos[i+4])
                        
                        # 转化成 center_x, center_y, w, h
                        center_x = (1.0 * (xmin + xmax) / 2.0) / image_w
                        center_y = (1.0 * (ymin + ymax) / 2.0) / image_h
                        w = (1.0 * (xmax - xmin)) / image_w
                        h = (1.0 * (ymax - ymin)) / image_h
                        
                        label[n_objects] = [center_x, center_y, w, h, class_index]
                        i += 5
                        n_objects += 1
                    
                    class_label, class_mask, box_label, object_mask, nobject_mask, object_num = \
                        self.process_label(label)
                        
                    self.train_dataset.put(
                        [image, class_label, class_mask, box_label, 
                         object_mask, nobject_mask, object_num])
                
        # 以多线程的方式进行数据预处理
        thread_list = []
        for i in range(n_thread):
            thread = Thread(target=_produce, args=(i,))
            thread_list.append(thread)
        for thread in thread_list:
            thread.start()
    
    def process_label(self, label):
        # true label and mask in 类别标记
        class_label = numpy.zeros(
            shape=(self.cell_size, self.cell_size, self.n_classes), 
            dtype='int32')
        class_mask = numpy.zeros(
            shape=(self.cell_size, self.cell_size),
            dtype='float32')
        
        # true_label and mask in 包围框标记
        box_label = numpy.zeros(
            shape=(self.cell_size, self.cell_size, self.max_objects, 4),
            dtype='float32')
        object_mask = numpy.zeros(
            shape=(self.cell_size, self.cell_size, self.max_objects), 
            dtype='float32')
        nobject_mask = numpy.ones(
            shape=(self.cell_size, self.cell_size, self.max_objects), 
            dtype='float32')
        
        object_num = numpy.zeros(
            shape=(self.max_objects), 
            dtype='int32')
        
        for j in range(self.max_objects):
            
            [center_x, center_y, w, h, class_index] = label[j]
            
            if class_index != 0:
                # 计算包围框标记
                center_cell_x = int(math.floor(self.cell_size * center_x - 1e-6))
                center_cell_y = int(math.floor(self.cell_size * center_y - 1e-6))
                box_label[center_cell_x, center_cell_y, j, :] = numpy.array(
                    [center_x, center_y, w, h])
                object_mask[center_cell_x, center_cell_y, j] = 1.0
                nobject_mask[center_cell_x, center_cell_y, j] = 0.0
                
                # 计算类别标记
                left_cell_x = int(math.floor(self.cell_size * (center_x - w / 2.0) - 1e-6))
                right_cell_x = int(math.floor(self.cell_size * (center_x + w / 2.0) - 1e-6))
                top_cell_y = int(math.floor(self.cell_size * (center_y - h / 2.0) - 1e-6))
                bottom_cell_y = int(math.floor(self.cell_size * (center_y + h / 2.0) - 1e-6))
                for x in range(left_cell_x, right_cell_x+1):
                    for y in range(top_cell_y, bottom_cell_y+1):
                        _class_label = numpy.zeros(
                            shape=[self.n_classes,], dtype='int32')
                        _class_label[int(class_index)-1] = 1
                        class_label[x, y, :] = _class_label
                        class_mask[x, y] = 1.0
                
                # object_num增加
                object_num[j] = 1.0
                            
        return class_label, class_mask, box_label, object_mask, nobject_mask, object_num
        
    def _shuffle_datasets(self, images, labels):
        index = list(range(images.shape[0]))
        random.shuffle(index)
        
        return images[index], labels[index]
    
    def get_train_batch(self, batch_size):
        batch_images, batch_class_labels, batch_class_masks, batch_box_labels, \
            batch_object_masks, batch_nobject_masks, batch_object_nums = [], [], [], [], [], [], []
            
        for i in range(batch_size):
            image, class_label, class_mask, box_label, \
                object_mask, nobject_mask, object_num = self.train_dataset.get()
            batch_images.append(image)
            batch_class_labels.append(class_label)
            batch_class_masks.append(class_mask)
            batch_box_labels.append(box_label)
            batch_object_masks.append(object_mask)
            batch_nobject_masks.append(nobject_mask)
            batch_object_nums.append(object_num)
        
        batch_images = numpy.array(batch_images, dtype='uint8')
        batch_class_labels = numpy.array(batch_class_labels, dtype='int32')
        batch_class_masks = numpy.array(batch_class_masks, dtype='float32')
        batch_box_labels = numpy.array(batch_box_labels, dtype='float32')
        batch_object_masks = numpy.array(batch_object_masks, dtype='float32')
        batch_nobject_masks = numpy.array(batch_nobject_masks, dtype='float32')
        batch_object_nums = numpy.array(batch_object_nums, dtype='int32')
            
        return batch_images, batch_class_labels, batch_class_masks, batch_box_labels, \
            batch_object_masks, batch_nobject_masks, batch_object_nums
            
    def get_valid_batch(self, i, batch_size):
        batch_images = self.valid_images[i: i+batch_size]
        batch_class_labels = self.valid_class_labels[i: i+batch_size]
        batch_class_masks = self.valid_class_masks[i: i+batch_size]
        batch_box_labels = self.valid_box_labels[i: i+batch_size]
        batch_object_masks = self.valid_object_masks[i: i+batch_size]
        batch_nobject_masks = self.valid_nobject_masks[i: i+batch_size]
        batch_object_nums = self.valid_object_nums[i: i+batch_size]
        
        return batch_images, batch_class_labels, batch_class_masks, batch_box_labels, \
            batch_object_masks, batch_nobject_masks, batch_object_nums
    
    def get_test_batch(self, i, batch_size):
        batch_images = self.test_images[i: i+batch_size]
        batch_class_labels = self.test_class_labels[i: i+batch_size]
        batch_class_masks = self.test_class_masks[i: i+batch_size]
        batch_box_labels = self.test_box_labels[i: i+batch_size]
        batch_object_masks = self.test_object_masks[i: i+batch_size]
        batch_nobject_masks = self.test_nobject_masks[i: i+batch_size]
        batch_object_nums = self.test_object_nums[i: i+batch_size]
        
        return batch_images, batch_class_labels, batch_class_masks, batch_box_labels, \
            batch_object_masks, batch_nobject_masks, batch_object_nums
        
    def data_augmentation(self, images, mode='train', flip=False, 
                          crop=False, crop_shape=(24,24,3), whiten=False, 
                          noise=False, noise_mean=0, noise_std=0.01):
        # 图像切割
        if crop:
            if mode == 'train':
                images = self._image_crop(images, shape=crop_shape)
            elif mode == 'test':
                images = self._image_crop_test(images, shape=crop_shape)
        # 图像翻转
        if flip:
            images = self._image_flip(images)
        # 图像白化
        if whiten:
            images = self._image_whitening(images)
        # 图像噪声
        if noise:
            images = self._image_noise(images, mean=noise_mean, std=noise_std)
            
        return images
    
    def _image_crop(self, images, shape):
        # 图像切割
        new_images = []
        for i in range(images.shape[0]):
            old_image = images[i,:,:,:]
            left = numpy.random.randint(old_image.shape[0] - shape[0] + 1)
            top = numpy.random.randint(old_image.shape[1] - shape[1] + 1)
            new_image = old_image[left: left+shape[0], top: top+shape[1], :]
            new_images.append(new_image)
        
        return numpy.array(new_images)
    
    def _image_crop_test(self, images, shape):
        # 图像切割
        new_images = []
        for i in range(images.shape[0]):
            old_image = images[i,:,:,:]
            left = int((old_image.shape[0] - shape[0]) / 2)
            top = int((old_image.shape[1] - shape[1]) / 2)
            new_image = old_image[left: left+shape[0], top: top+shape[1], :]
            new_images.append(new_image)
        
        return numpy.array(new_images)
    
    def _image_flip(self, images):
        # 图像翻转
        for i in range(images.shape[0]):
            old_image = images[i,:,:,:]
            if numpy.random.random() < 0.5:
                new_image = cv2.flip(old_image, 1)
            else:
                new_image = old_image
            images[i,:,:,:] = new_image
        
        return images
    
    def _image_whitening(self, images):
        # 图像白化
        for i in range(images.shape[0]):
            old_image = images[i,:,:,:]
            new_image = (old_image - numpy.mean(old_image)) / numpy.std(old_image)
            images[i,:,:,:] = new_image
        
        return images
    
    def _image_noise(self, images, mean=0, std=0.01):
        # 图像噪声
        for i in range(images.shape[0]):
            old_image = images[i,:,:,:]
            new_image = old_image
            for i in range(image.shape[0]):
                for j in range(image.shape[1]):
                    for k in range(image.shape[2]):
                        new_image[i, j, k] += random.gauss(mean, std)
            images[i,:,:,:] = new_image
        
        return images