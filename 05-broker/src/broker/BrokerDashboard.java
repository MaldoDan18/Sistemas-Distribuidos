package broker;

import java.awt.BorderLayout;
import java.awt.Color;
import java.awt.Component;
import java.awt.Dimension;
import javax.swing.JFrame;
import javax.swing.JScrollPane;
import javax.swing.JTable;
import javax.swing.SwingUtilities;
import javax.swing.Timer;
import javax.swing.table.DefaultTableCellRenderer;
import javax.swing.table.DefaultTableModel;

public class BrokerDashboard {
    private final BrokerRemote service;
    private final DefaultTableModel model;

    public BrokerDashboard(BrokerRemote service) {
        this.service = service;
        this.model = new DefaultTableModel(
            new Object[] {"Sale ID", "Estado", "Servidor", "Clientes", "Hilos", "Actualizado", "Resumen"},
            0
        ) {
            @Override
            public boolean isCellEditable(int row, int column) {
                return false;
            }
        };
    }

    public void show() {
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("Broker RMI - Estados de venta");
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            frame.setLayout(new BorderLayout());

            JTable table = new JTable(model);
            table.setFillsViewportHeight(true);
            table.setRowHeight(26);
            table.getColumnModel().getColumn(1).setCellRenderer(new StatusRenderer());

            JScrollPane pane = new JScrollPane(table);
            pane.setPreferredSize(new Dimension(1080, 380));
            frame.add(pane, BorderLayout.CENTER);

            Timer timer = new Timer(350, e -> refresh());
            timer.start();

            frame.pack();
            frame.setLocationRelativeTo(null);
            frame.setVisible(true);
        });
    }

    private void refresh() {
        try {
            BrokerSnapshot snapshot = service.getSnapshot();
            model.setRowCount(0);
            for (SaleStatus sale : snapshot.sales) {
                String clients = sale.connectedClients + "/" + sale.expectedClients;
                model.addRow(new Object[] {
                    sale.saleId,
                    sale.status,
                    sale.server,
                    clients,
                    sale.buyerThreads,
                    sale.updatedAt,
                    sale.summary == null ? "" : sale.summary
                });
            }
        } catch (Exception ignored) {
            // The broker UI should keep running even if a transient remote error occurs.
        }
    }

    private static class StatusRenderer extends DefaultTableCellRenderer {
        @Override
        public Component getTableCellRendererComponent(
            JTable table,
            Object value,
            boolean isSelected,
            boolean hasFocus,
            int row,
            int column
        ) {
            Component c = super.getTableCellRendererComponent(table, value, isSelected, hasFocus, row, column);
            String status = value == null ? "" : value.toString().toLowerCase();

            if ("blue".equals(status)) {
                c.setBackground(new Color(44, 107, 237));
                c.setForeground(Color.WHITE);
            } else if ("orange".equals(status)) {
                c.setBackground(new Color(242, 139, 37));
                c.setForeground(Color.WHITE);
            } else if ("green".equals(status)) {
                c.setBackground(new Color(43, 191, 106));
                c.setForeground(Color.WHITE);
            } else {
                c.setBackground(new Color(141, 141, 141));
                c.setForeground(Color.WHITE);
            }

            return c;
        }
    }
}
