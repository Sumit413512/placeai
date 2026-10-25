/* PlaceAI on-device detector. No media or inference data leaves this worker. */
'use strict';
let detector;
self.onmessage=async ({data})=>{
  try {
    if(data.type==='load'){
      // Pinned @tensorflow/tfjs@4.22.0 and @tensorflow-models/coco-ssd@2.2.3.
      self.postMessage({type:'phase',label:'Loading runtime'});
      importScripts('/static/vendor/proctor-v1/tf.min.js','/static/vendor/proctor-v1/tf-backend-wasm.min.js','/static/vendor/proctor-v1/coco-ssd.min.js');
      self.tf.wasm.setWasmPaths('/static/vendor/proctor-v1/');
      self.tf.wasm.setThreadsCount(1);
      if(!await self.tf.setBackend('wasm'))throw new Error('Detector runtime is unsupported');
      await self.tf.ready();
      self.postMessage({type:'phase',label:'Downloading detector'});
      const base=new URL('/static/vendor/proctor-v1/',self.location.origin).href;
      detector=await self.cocoSsd.load({base:'lite_mobilenet_v2',modelUrl:base+'model.json'});
      self.postMessage({type:'phase',label:'Checking detector'});
      const input=self.tf.zeros([240,320,3],'int32');
      try{await detector.detect(input,10,0.32);}finally{input.dispose();}
      self.postMessage({type:'ready'});
    }else if(data.type==='detect'){
      if(!detector)throw new Error('Detector is not ready');
      const input=self.tf.browser.fromPixels(new ImageData(new Uint8ClampedArray(data.pixels),data.width,data.height));
      try{
        const predictions=await detector.detect(input,data.maxNumBoxes,data.minScore);
        self.postMessage({type:'result',id:data.id,predictions});
      }finally{input.dispose();}
    }
  }catch(error){
    console.error("PlaceAI detector: "+error.message);
    self.postMessage({type:'error',id:data.id,message:data.type==='load'?'Detector preparation failed':'Detector inference failed'});
  }
};
