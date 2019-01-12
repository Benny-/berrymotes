'use strict';

(async () => {
  const rawResponse = await fetch('//mylittleserver.nl/emojis/all-reddit-emojis.json')
  const emotes = await rawResponse.json()
  const container = document.querySelector('body')
  for(let i = 0; i < emotes.length && i < 2000; i++) {
      const emote = emotes[i]
      
      const anchor = document.createElement('a')
      anchor.href = emote.base_img_src
      
      const img = document.createElement('img')
      img.width = emote.width
      img.height = emote.height
      img.src = emote.base_img_src
      img.title = emote.canonical
      
      // TODO: Add hover style.
      
      anchor.appendChild(img)
      container.appendChild(anchor)
  }
})();

