(function(){
  'use strict';
  let posting=false;
  let loadingMore=false;
  let noMore=false;
  let lastLoadAt=0;
  let lastHeight=0;
  const formSelector='.comment-form';
  function formState(form,disabled){
    form.querySelectorAll('input,button').forEach(el=>el.disabled=disabled);
    const btn=form.querySelector('button');
    if(btn)btn.textContent=disabled?'Posting…':'Post';
  }
  document.addEventListener('submit',function(e){
    const form=e.target.closest(formSelector);
    if(!form)return;
    if(posting){e.preventDefault();e.stopImmediatePropagation();return;}
    const input=form.querySelector('input');
    if(!input||!input.value.trim())return;
    posting=true;
    form.dataset.reeloPosting='1';
    formState(form,true);
    window.setTimeout(function(){
      posting=false;
      delete form.dataset.reeloPosting;
      if(document.body.contains(form))formState(form,false);
    },12000);
  },true);
  document.addEventListener('click',function(e){
    const send=e.target.closest('.comment-form button');
    if(send&&send.disabled){e.preventDefault();e.stopImmediatePropagation();}
  },true);
  const list=document.getElementById('commentList');
  if(!list)return;
  function canLoad(){
    if(loadingMore||noMore||typeof window.loadComments!=='function')return false;
    const now=Date.now();
    if(now-lastLoadAt<1200)return false;
    return list.scrollTop+list.clientHeight>=list.scrollHeight-180;
  }
  function loadMore(){
    if(!canLoad())return;
    loadingMore=true;
    lastLoadAt=Date.now();
    const before=list.scrollHeight;
    lastHeight=before;
    Promise.resolve(window.loadComments(false)).then(function(){
      window.setTimeout(function(){
        const after=list.scrollHeight;
        if(after<=before||after<=lastHeight)noMore=true;
      },150);
    }).catch(function(){}).finally(function(){loadingMore=false;});
  }
  list.addEventListener('scroll',loadMore,{passive:true});
  const observer=new MutationObserver(function(){
    if(list.scrollHeight>lastHeight+40)noMore=false;
  });
  observer.observe(list,{childList:true,subtree:true});
  document.addEventListener('click',function(e){
    if(e.target.closest('[onclick*="openComments"],#commentButton,.comment-trigger')){
      noMore=false;
      lastHeight=0;
    }
  },true);
})();
