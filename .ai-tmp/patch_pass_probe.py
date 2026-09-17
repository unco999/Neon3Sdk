import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

anchor = """                    pass.set_pipeline(pipeline);
                    pass.set_bind_group(0, &self.view_bind_group, &[]);
                    pass.set_bind_group(1, &self.resident_font.as_ref().unwrap().bind_group, &[]);
                    pass.set_vertex_buffer(0, self.text_material_buffer.slice(..));
                    pass.draw(0..6, *start..*start + *count);"""
assert anchor in d, 'pass draw anchor missing'
probe = """                    if package_id == "text-type-in" || package_id == "text-delete-fragment" {
                        eprintln!(
                            "EDITOR_FX pass package={package_id} start={start} count={count} first_rect={:?}",
                            self.text_material_instances.get(*start as usize).map(|i| i.rect)
                        );
                    }
                    pass.set_pipeline(pipeline);
                    pass.set_bind_group(0, &self.view_bind_group, &[]);
                    pass.set_bind_group(1, &self.resident_font.as_ref().unwrap().bind_group, &[]);
                    pass.set_vertex_buffer(0, self.text_material_buffer.slice(..));
                    pass.draw(0..6, *start..*start + *count);"""
d = d.replace(anchor, probe, 1)

# store instances on self so probe can read them: check if text_material_instances field exists
if 'text_material_instances' not in d:
    # find ordered_text_materials write and stash a copy
    anchor2 = """            queue.write_buffer(
                &self.text_material_buffer,
                0,
                bytemuck::cast_slice(&ordered_text_materials),
            );"""
    assert anchor2 in d, 'write anchor missing'
    stash = """            self.text_material_instances = ordered_text_materials.clone();
            queue.write_buffer(
                &self.text_material_buffer,
                0,
                bytemuck::cast_slice(&ordered_text_materials),
            );"""
    d = d.replace(anchor2, stash, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('pass probe installed (field referenced; must declare)')
