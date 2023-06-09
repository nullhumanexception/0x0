#!/usr/bin/env python3

"""
    Copyright © 2020 Mia Herkt
    Licensed under the EUPL, Version 1.2 or - as soon as approved
    by the European Commission - subsequent versions of the EUPL
    (the "License");
    You may not use this work except in compliance with the License.
    You may obtain a copy of the license at:

        https://joinup.ec.europa.eu/software/page/eupl

    Unless required by applicable law or agreed to in writing,
    software distributed under the License is distributed on an
    "AS IS" basis, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
    either express or implied.
    See the License for the specific language governing permissions
    and limitations under the License.
"""

import numpy as np
import os
import sys
from io import BytesIO
from pathlib import Path

os.environ["GLOG_minloglevel"] = "2"  # seriously :|
import caffe
import av
av.logging.set_level(av.logging.PANIC)

class NSFWDetector:
    def __init__(self):
        npath = Path(__file__).parent / "nsfw_model"
        self.nsfw_net = caffe.Net(
            str(npath / "deploy.prototxt"),
            caffe.TEST,
            weights = str(npath / "resnet_50_1by2_nsfw.caffemodel")
        )
        self.caffe_transformer = caffe.io.Transformer({
            'data': self.nsfw_net.blobs['data'].data.shape
        })
        # move image channels to outermost
        self.caffe_transformer.set_transpose('data', (2, 0, 1))
        # subtract the dataset-mean value in each channel
        self.caffe_transformer.set_mean('data', np.array([104, 117, 123]))
        # rescale from [0, 1] to [0, 255]
        self.caffe_transformer.set_raw_scale('data', 255)
        # swap channels from RGB to BGR
        self.caffe_transformer.set_channel_swap('data', (2, 1, 0))

    def _compute(self, img):
        image = caffe.io.load_image(img)

        H, W, _ = image.shape
        _, _, h, w = self.nsfw_net.blobs["data"].data.shape
        h_off = int(max((H - h) / 2, 0))
        w_off = int(max((W - w) / 2, 0))
        crop = image[h_off:h_off + h, w_off:w_off + w, :]

        transformed_image = self.caffe_transformer.preprocess('data', crop)
        transformed_image.shape = (1,) + transformed_image.shape

        input_name = self.nsfw_net.inputs[0]
        output_layers = ["prob"]
        all_outputs = self.nsfw_net.forward_all(
            blobs=output_layers, **{input_name: transformed_image})

        outputs = all_outputs[output_layers[0]][0].astype(float)

        return outputs

    def detect(self, fpath):
        try:
            with av.open(fpath) as container:
                try: container.seek(int(container.duration / 2))
                except: container.seek(0)

                frame = next(container.decode(video=0))

                if frame.width >= frame.height:
                    w = 256
                    h = int(frame.height * (256 / frame.width))
                else:
                    w = int(frame.width * (256 / frame.height))
                    h = 256
                frame = frame.reformat(width=w, height=h, format="rgb24")
                img = BytesIO()
                frame.to_image().save(img, format="ppm")

            scores = self._compute(img)
        except:
            return -1.0

        return scores[1]


if __name__ == "__main__":
    n = NSFWDetector()

    for inf in sys.argv[1:]:
        score = n.detect(inf)
        print(inf, score)
