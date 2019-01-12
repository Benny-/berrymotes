# Server filler

A typical invocation looks like this:

```bash
./server-filler/main.py ./scrape_workmap/output/ ./emojis/ && rsync -avz --safe-links --progress ./emojis/ 'username@yourserver:/var/www/emojis/'
```
