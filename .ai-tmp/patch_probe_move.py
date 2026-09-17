import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

# remove the misplaced probe (before Destroy mirrors)
misplaced = """        for (path, state) in &self.editors {
            if !state.edit_fx.is_empty() {
                eprintln!(
                    "EDITOR_FX mirror {path} fx={} pkg0={}",
                    state.edit_fx.len(),
                    state.edit_fx[0].package_id
                );
            }
        }
        // Destroy mirrors whose presentations disappeared."""
assert misplaced in d, 'misplaced probe missing'
d = d.replace(misplaced, "        // Destroy mirrors whose presentations disappeared.", 1)

# add probe after Create / update mirrors loop (end of reconcile_editors)
anchor = """            } else {
                self.editors.insert(
                    path,
                    EditorRuntimeState::from_presentation(declaration, presentation),
                );
            }
        }
    }

    /// Attaches the ui-runtime input sink (host bridge)."""
assert anchor in d, 'end anchor missing'
probe = """            } else {
                self.editors.insert(
                    path,
                    EditorRuntimeState::from_presentation(declaration, presentation),
                );
            }
        }
        for (path, state) in &self.editors {
            if !state.edit_fx.is_empty() {
                eprintln!(
                    "EDITOR_FX mirror {path} fx={} pkg0={}",
                    state.edit_fx.len(),
                    state.edit_fx[0].package_id
                );
            }
        }
    }

    /// Attaches the ui-runtime input sink (host bridge)."""
d = d.replace(anchor, probe, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('probe moved to end of reconcile_editors')
