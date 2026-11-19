import './style.css';
import { FFmpeg } from '@ffmpeg/ffmpeg';
import { toBlobURL } from '@ffmpeg/util';
const $ = id => document.getElementById(id);
const imageTypes = /\.(heic|heif|jpg|jpeg|png|webp|gif)$/i;
const videoTypes = /\.(mp4|mov|webm|mkv|avi)$/i;
let jobs = [], busy = false, engine, heicLoader;
function render() {
  $('queue').replaceChildren();
  for (const job of jobs) {
    const row = document.createElement('li');
    const name = document.createElement('span'); name.className = 'name'; name.textContent = job.file.name;
    const detail = document.createElement('small'); detail.textContent = `${(job.file.size / 1e6).toFixed(1)} MB · ${job.status}`;
    name.append(detail); row.append(name);
    if (job.url) { const link = document.createElement('a'); link.href = job.url; link.download = job.name; link.textContent = 'Download'; row.append(link); }
    $('queue').append(row);
  }
  $('count').textContent = jobs.length; $('empty').hidden = jobs.length > 0;
  $('convert').disabled = busy || !jobs.length;
  for (const id of ['clear','drop','format','quality']) $(id).disabled = busy;
}
function add(files) {
  if (busy) return;
  const errors = [];
  for (const file of files) {
    const image = imageTypes.test(file.name);
    let error;
    if (!image && !videoTypes.test(file.name)) error = 'unsupported file type';
    else if (!file.size) error = 'empty file';
    else if (file.size > (image ? 20 : 100) * 1e6) error = image ? 'image exceeds 20 MB' : 'video exceeds 100 MB';
    else if (jobs.length >= 10) error = '10-file limit reached';
    else if (jobs.reduce((n,j) => n+j.file.size,0)+file.size > 200e6) error = 'batch exceeds 200 MB';
    if (error) { errors.push(`${file.name}: ${error}`); continue; }
    jobs.push({file,image,status:'Ready'});
  }
  $('status').textContent = errors.join(' · ') || 'Ready to convert.'; render();
}
$('files').accept = '.heic,.heif,.jpg,.jpeg,.png,.webp,.gif,.mp4,.mov,.webm,.mkv,.avi';
$('drop').onclick = () => $('files').click();
$('files').onchange = e => {add(e.target.files);e.target.value='';};
$('drop').ondragover = e => {e.preventDefault();$('drop').classList.add('over');};
$('drop').ondragleave = () => $('drop').classList.remove('over');
$('drop').ondrop = e => {e.preventDefault();$('drop').classList.remove('over');add(e.dataTransfer.files);};
$('clear').onclick = () => {jobs.forEach(j=>j.url && URL.revokeObjectURL(j.url)); jobs=[]; render();$('status').textContent='Queue cleared.';};
$('format').onchange = () => {$('hint').textContent = ['mp4','webm','gif'].includes($('format').value) ? 'Video outputs require a video input. GIF is limited to 720 px and 12 fps.' : 'Images use the first frame. JPG uses a white background.';};
async function loadHeic() {
  if (!heicLoader) heicLoader = new Promise((resolve,reject)=>{
    const script = document.createElement('script'); script.src='https://cdn.jsdelivr.net/npm/heic2any@0.0.4/dist/heic2any.min.js';
    script.onload=resolve;script.onerror=()=>{heicLoader=null;script.remove();reject(new Error('HEIC tools could not download. Check your connection and retry.'));};document.head.append(script);
  });
  await heicLoader;
}
async function imageOutput(blob, fmt, quality) {
  if (/\.hei[cf]$/i.test(blob.name || '')) {
    await loadHeic();
    blob = await window.heic2any({blob,toType:'image/png'});
    if (Array.isArray(blob)) blob = blob[0];
  }
  const bitmap = await createImageBitmap(blob);
  try {
    if (bitmap.width*bitmap.height > 40e6) throw new Error('Image exceeds the 40-megapixel limit.');
    const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;
    const ctx=canvas.getContext('2d');
    if(fmt==='jpg'){ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);}
    ctx.drawImage(bitmap,0,0);
    const mime=`image/${fmt==='jpg'?'jpeg':fmt}`;
    const result=await new Promise(resolve=>canvas.toBlob(resolve,mime,quality));
    canvas.width=canvas.height=0;
    if(!result || result.type!==mime) throw new Error('Your browser cannot encode this format.');
    return result;
  } finally {bitmap.close();}
}
async function videoOutput(file, fmt, quality) {
  engine=new FFmpeg();
  const urls=[];
  try {
    $('status').textContent='Loading video tools (about 32 MB on first use)…';
    const base='https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.12.10/dist/esm';
    urls.push(await toBlobURL(`${base}/ffmpeg-core.js`,'text/javascript'));
    urls.push(await toBlobURL(`${base}/ffmpeg-core.wasm`,'application/wasm'));
    await engine.load({coreURL:urls[0],wasmURL:urls[1]});
    const input='input.'+file.name.split('.').pop().toLowerCase(), output='output.'+fmt;
    await engine.writeFile(input,new Uint8Array(await file.arrayBuffer()));
    engine.on('progress',({progress})=>{$('status').textContent=`Converting video… ${Math.min(99,Math.max(0,Math.round(progress*100)))}%`;});
    let args;
    if(['jpg','png','webp'].includes(fmt)) args=['-frames:v','1'];
    else if(fmt==='gif') args=['-vf','fps=12,scale=720:-2:force_original_aspect_ratio=decrease','-an'];
    else args=['-map','0:v:0','-map','0:a:0?','-vf','scale=trunc(iw/2)*2:trunc(ih/2)*2','-c:v',fmt==='mp4'?'libx264':'libvpx',...(fmt==='mp4'?['-preset','ultrafast','-crf',quality>.9?'18':quality<.8?'28':'23']:['-b:v','1500k']),'-pix_fmt','yuv420p','-c:a',fmt==='mp4'?'aac':'libvorbis'];
    const code=await engine.exec(['-i',input,...args,output],120000);
    if(code!==0) throw new Error('Conversion failed or exceeded two minutes. Try a shorter clip or the Windows app.');
    const bytes=await engine.readFile(output);
    return new Blob([bytes],{type:({jpg:'image/jpeg',png:'image/png',webp:'image/webp',gif:'image/gif',mp4:'video/mp4',webm:'video/webm'})[fmt]});
  } finally {engine.terminate();engine=null;urls.forEach(URL.revokeObjectURL);}
}
$('convert').onclick=async()=>{
  busy=true;render();let saved=0;
  const fmt=$('format').value,quality=Number($('quality').value);
  for(const job of jobs){
    if(job.url){URL.revokeObjectURL(job.url);job.url=null;}
    job.status='Converting…';render();
    try{
      if(job.image && ['mp4','webm','gif'].includes(fmt)) throw new Error('Choose JPG, PNG or WebP for image inputs.');
      $('status').textContent=`Converting ${job.file.name}…`;
      const result=await (job.image?imageOutput(job.file,fmt,quality):videoOutput(job.file,fmt,quality));
      job.url=URL.createObjectURL(result);job.name=job.file.name.replace(/\.[^.]+$/,'')+'-converted.'+fmt;job.status='Ready to download';saved++;
    }catch(error){job.status=error.message || 'This file could not be decoded. Try the Windows app.';}
    render();
  }
  busy=false;render();$('status').textContent=`${saved} of ${jobs.length} converted. Download each result above.`;
};
