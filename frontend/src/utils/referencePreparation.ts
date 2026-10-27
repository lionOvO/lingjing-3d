export type Bounds={left:number;top:number;right:number;bottom:number}

// Restore source pixels, rather than repainting or hallucinating missing parts.
// Interpolation keeps fast pointer movements from leaving holes in the mask.
export function paintForeground(pixels:Uint8ClampedArray,original:Uint8ClampedArray,width:number,height:number,from:{x:number;y:number},to:{x:number;y:number},radius:number,restore:boolean,shape:'circle'|'square'='circle'){
  // Snap a one-pixel brush to pixel centres, even at fractional zoom levels.
  if(radius<=.5){from={x:Math.floor(from.x)+.5,y:Math.floor(from.y)+.5};to={x:Math.floor(to.x)+.5,y:Math.floor(to.y)+.5}}
  const steps=Math.max(1,Math.ceil(Math.hypot(to.x-from.x,to.y-from.y)/Math.max(1,radius*.5)))
  for(let step=0;step<=steps;step++){
    const cx=from.x+(to.x-from.x)*step/steps,cy=from.y+(to.y-from.y)*step/steps
    for(let row=Math.max(0,Math.floor(cy-radius));row<Math.min(height,Math.ceil(cy+radius));row++)
      for(let col=Math.max(0,Math.floor(cx-radius));col<Math.min(width,Math.ceil(cx+radius));col++){
        const dx=Math.abs(col+.5-cx),dy=Math.abs(row+.5-cy)
        if(shape==='circle'?dx**2+dy**2>radius**2:dx>radius||dy>radius)continue
        const i=(row*width+col)*4
        if(restore)pixels.set(original.subarray(i,i+4),i)
        else pixels[i+3]=0
      }
  }
}

export function fitReference(bounds:Bounds,margin:number,size=1024){
  const width=bounds.right-bounds.left,height=bounds.bottom-bounds.top
  if(width<=0||height<=0)throw new Error('裁剪区域没有可见主体，请调整范围')
  const usable=size*(1-Math.max(0,Math.min(24,margin))*2/100)
  const scale=Math.min(usable/width,usable/height)
  return {x:(size-width*scale)/2,y:(size-height*scale)/2,width:width*scale,height:height*scale}
}

// Bounded unsharp mask; transparent edges remain untouched to avoid halos.
export function sharpenReference(pixels:Uint8ClampedArray,width:number,height:number){
  const result=new Uint8ClampedArray(pixels)
  for(let y=1;y<height-1;y++)for(let x=1;x<width-1;x++){
    const index=(y*width+x)*4
    const neighbors=[index-width*4,index+width*4,index-4,index+4]
    if(pixels[index+3]<250||neighbors.some(i=>pixels[i+3]<250))continue
    for(let c=0;c<3;c++){
      const average=neighbors.reduce((sum,i)=>sum+pixels[i+c],0)/4
      const edge=pixels[index+c]-average
      if(Math.abs(edge)>3)result[index+c]=pixels[index+c]+Math.max(-8,Math.min(8,edge*.2))
    }
  }
  return result
}
