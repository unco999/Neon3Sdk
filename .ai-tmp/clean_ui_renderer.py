import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

old1 = '''                    if package_id == "text-type-in" || package_id == "text-delete-fragment" {
                        eprintln!(
                            "EDITOR_FX pass package={package_id} start={start} count={count} first_rect={:?}",
                            self.text_material_instances.get(*start as usize).map(|i| i.rect)
                        );
                    }
'''
d = d.replace(old1, '', 1)

old2 = '''                    let Some(pipeline) = self.text_material_pipelines.get(package_id) else {
                        eprintln!("EDITOR_FX MISSING pipeline for package {package_id}");
                        continue;
                    };'''
new2 = '''                    let Some(pipeline) = self.text_material_pipelines.get(package_id) else {
                        continue;
                    };'''
d = d.replace(old2, new2, 1)

old3 = '''            self.text_material_instances = ordered_text_materials.clone();
            queue.write_buffer(
                &self.text_material_buffer,
                0,
                bytemuck::cast_slice(&ordered_text_materials),
            );'''
new3 = '''            queue.write_buffer(
                &self.text_material_buffer,
                0,
                bytemuck::cast_slice(&ordered_text_materials),
            );'''
d = d.replace(old3, new3, 1)

old4 = '''    text_material_buffer: wgpu::Buffer,
    text_material_instances: Vec<UiTextInstance>,
    text_material_capacity: usize,'''
new4 = '''    text_material_buffer: wgpu::Buffer,
    text_material_capacity: usize,'''
d = d.replace(old4, new4, 1)

old5 = '''            text_material_buffer: create_text_buffer(device, 512),
            text_material_instances: Vec::new(),
            text_material_capacity: 512,'''
new5 = '''            text_material_buffer: create_text_buffer(device, 512),
            text_material_capacity: 512,'''
d = d.replace(old5, new5, 1)

io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('ui_renderer cleaned; EDITOR_FX remaining:', d.count('EDITOR_FX'))
