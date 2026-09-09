(function(){
  'use strict';
  let posting=false;
  let loadingMore=false;
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
  if(list){
    list.addEventListener('scroll',function(){
      if(loadingMore||typeof window.loadComments!=='function')return;
      if(list.scrollTop+list.clientHeight<list.scrollHeight-180)return;
      const total=Number(window.commentTotal||0);
      const offset=Number(window.commentOffset||0);
      if(total&&offset>=total)return;
      loadingMore=true;
      Promise.resolve(window.loadComments(false)).finally(function(){loadingMore=false;});
    });
  }
})();
