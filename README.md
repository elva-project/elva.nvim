<!-- badges -->

# ELVA Neovim Real-time Collaboration Plugin



During development I'm using this ugly line to Update the Plugin and start nvim and connect to the elva server in one command

```bash
$ nvim -u vimrc --headless  -c "UpdateRemotePlugins" -c "q"  2>&1|  grep 'registered plugins' | grep 'elva_nvim'  && nvim -u vimrc -c "ElvaConnect localhost 8089 1234567890"
```

## Roadmap

### Functionality

- [x] bidirectional text sync
  - [x] text sync from ytext to neovim buffer
  - [x] text sync from neovim buffer to ytext
- [ ] bidirectional awareness sync
  - [ ] awareness sync from ydoc to neovim
  - [ ] awareness sync from neovim to ydoc
- [x] efficient text delta passing between Neovim and plugin
- [ ] session management (grouping of documents)


### UI

- [ ] `ElvaConnect` command to connect to a document or session on a host
- [ ] `ElvaDisconnect` command to disconnect
- [ ] `ElvaServe` command to host a document or session
- [ ] `ElvaConfig` command to manage plugin options
- [ ] visualization of the current status (document, connection, peers)


### Compatibility

- [ ] ELVA editor app
- [ ] ELVA Emacs plugin `elva.el`
- [ ] Visual Studio Code


### Utilities

- [ ] decorator to not have explicit function arguments and not just `args: list`


### Testing

- [ ] bidirectional text sync
  - [ ] text sync from ytext to neovim buffer
  - [ ] text sync from neovim buffer to ytext
- [ ] bidirectional awareness sync
  - [ ] awareness sync from ydoc to neovim
  - [ ] awareness sync from neovim to ydoc
- [ ] efficient text delta passing between Neovim and plugin
- [ ] session management (grouping of documents)


## Development

- environment setup

  ```sh
  uv venv
  ```

- pre-commit git hooks for compliance with code style

  ```sh
  prek install --config prek.yml
  ```

- testing

  ```sh
  pytest
  ```

- code coverage

  ```sh
  coverage run -m pytest
  ```
